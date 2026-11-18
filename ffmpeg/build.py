#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 FreeKC
"""The FFmpeg program of Immuch360 Desktop: its sources, its build, its gate, its archive and its release.

Immuch360 Desktop turns flat videos into 3D side by side videos (release 49, store/m2/release-49/lots/video3d-plan.md of
the app's notes). It runs FFmpeg as a separate program, downloaded when the user asks for it: one process decodes the
source to raw RGB frames on a pipe, another encodes raw side by side frames from a pipe, a third joins the segments
with the source's sound and the 3D marking. This script makes that program, ffmpeg and ffprobe with their shared
libraries, under the LGPL 2.1 or later, for Windows x64, Linux x64 and macOS (arm64 and x86_64 in one), from the sources
of sources.lock next to it. The jobs of .github/workflows/ffmpeg.yml run it; it uses the Python standard library only
and writes no cache next to itself.

  build.py lock --system SYSTEM [--github-output]
      the id, the name of the archive, the container and the tools of SYSTEM (windows-x64, linux-x64, macos-universal)
  build.py sources --dir DIR [--cache DIR] [--system SYSTEM]
      every archive of the lock (of SYSTEM, or all) downloaded into the cache (DIR/archives by default), checked by its
      size and SHA-256, and unpacked into DIR/<name>; FFmpeg's RELEASE file must be the version of the lock, and the
      components pulled by configure (the _select lines of FFmpeg's configure) must be those the lock lists
  build.py build --system SYSTEM --src DIR --work DIR [--jobs N]
      nasm, then zlib, zimg, SVT-AV1, dav1d (and libva on Linux) as static libraries (libva shared), then FFmpeg with
      the configure options of the lock, for each architecture (macOS: arm64 natively and x86_64 cross compiled, then
      joined by lipo and signed ad hoc); the programs and libraries laid out as the archive holds them in WORK/stage,
      and WORK/build.json: the configure lines, the tool versions, config.h and the components configure enabled,
      which must be those of the lock (CONFIG_GPL 0, CONFIG_NONFREE 0, CONFIG_VERSION3 0)
  build.py licences [--src DIR]
      each text of licenses/ equal to the file of the sources it comes from (sources.lock, "licences"), and no other
      text; every file compiled from the libraries whose header grants another licence than its library's carried,
      with its copyright holders, by one of them (sources.lock, "notice_scan")
  build.py archive --system SYSTEM --work DIR --src DIR --out DIR --tag TAG [--commit SHA] [--repo OWNER/NAME]
      Immuch360-ffmpeg-<version>-<build>-<system>.zip: bin/ (and lib/), licenses/, BUILD-INFO.txt, SHA256SUMS.txt; sorted
      names, fixed dates and modes, so that the same files give the same bytes
  build.py check --system SYSTEM --archive FILE [--run] [--arch-x86-64] [--report FILE]
      the gate: the files, their sums, the licence texts, the libraries and imports of every program and library (the
      system's and the archive's own only), the size; with --run the programs themselves: -buildconf without a GPL,
      non free or version 3 option and with every option of the lock, -L naming the LGPL 2.1 or later, and the lists
      of -encoders, -decoders, -muxers, -demuxers, -filters, -protocols and -bsfs equal to those of the lock
  build.py program --system windows-x64 --archive FILE --out DIR
      the .exe and .dll files of the archive, written in DIR/bin for the signing step
  build.py signed --system windows-x64 --archive FILE --signed DIR --out DIR
      the archive again with the files of DIR/bin, each the file of the archive with an Authenticode signature added
      and nothing else changed; BUILD-INFO.txt says so, SHA256SUMS.txt gives the new sums
  build.py source-archive --src DIR --cache DIR --builds DIR --out FILE --tag TAG [--commit SHA]
      the corresponding source of a release: every archive of the lock as downloaded, this recipe (ffmpeg/ and the
      workflow) and the BUILD-INFO.txt of each archive with its exact configure lines, as one tar.xz
  build.py verify --dir DIR --tag TAG
      the assets of a release downloaded again into DIR, against its SHA256SUMS.txt and ffmpeg-lgpl-<tag>.json
  build.py release --archives DIR --sources FILE --out DIR --tag TAG --commit SHA --run ID [--repo OWNER/NAME]
                   [--notes FILE] [--require-signed-windows]
      the files of a release: the three archives checked again and built from one commit, ffmpeg-lgpl-<tag>.json (each
      archive with its address, size and SHA-256, and every file with its size, SHA-256 and mode), SHA256SUMS.txt

Exit codes: 0 good, 1 a check failed, 2 bad arguments or missing inputs.
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import io
import json
import lzma
import os
import pathlib
import platform
import re
import shlex
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import zipfile

sys.dont_write_bytecode = True

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
LOCK = HERE / 'sources.lock'
LICENCES = HERE / 'licenses'
WORKFLOW = ROOT / '.github' / 'workflows' / 'ffmpeg.yml'
SYSTEMS = ('windows-x64', 'linux-x64', 'macos-universal')
REPOSITORY = 'immuch360/libmpv-builds'
# Our own texts of licenses/, written for the archive rather than copied from a source
OWN_TEXTS = ('README.md', 'PATENTS-NOTE.md')
SOURCE_NOTE = 'licenses/FFmpeg-SOURCE.txt'
KINDS = ('encoder', 'decoder', 'demuxer', 'muxer', 'parser', 'bsf', 'filter', 'protocol', 'indev')
# The generated list of each kind in the build tree of FFmpeg (configure's print_enabled_components)
LIST_FILES = {'encoder': 'libavcodec/codec_list.c', 'decoder': 'libavcodec/codec_list.c',
              'parser': 'libavcodec/parser_list.c', 'bsf': 'libavcodec/bsf_list.c',
              'demuxer': 'libavformat/demuxer_list.c', 'muxer': 'libavformat/muxer_list.c',
              'filter': 'libavfilter/filter_list.c', 'protocol': 'libavformat/protocol_list.c',
              'indev': 'libavdevice/indev_list.c'}
# The listing options of the program and the kinds they show
LISTINGS = {'encoder': '-encoders', 'decoder': '-decoders', 'muxer': '-muxers', 'demuxer': '-demuxers',
            'filter': '-filters', 'protocol': '-protocols', 'bsf': '-bsfs'}
LGPL_LINE = ('under the terms of the GNU Lesser General Public License as published by the Free Software Foundation; '
             'either version 2.1 of the License, or (at your option) any later version')
SIGNED_LINE = ('Signed: every .exe and .dll by APROGSYS with Azure Artifact Signing (Authenticode, SHA-256, RFC 3161 '
               'timestamp of Microsoft)')
CONFIG_FLAGS = ('CONFIG_GPL', 'CONFIG_NONFREE', 'CONFIG_VERSION3')
# Every build configures FFmpeg with this prefix first (the files are installed elsewhere through DESTDIR), so the
# configure line that libavutil keeps starts with it
PREFIX = '/immuch360-ffmpeg'
CONFIGURATION_START = f'--prefix={PREFIX}'.encode()


class Failure(Exception):
    pass


# --- the lock ----------------------------------------------------------------------------------------------------

def load_lock(path: pathlib.Path = LOCK) -> dict:
    lock = json.loads(path.read_text(encoding='utf-8'))
    for key in ('id', 'ffmpeg', 'sources', 'containers', 'configure', 'components', 'pulled', 'printed', 'licences',
                'permissive', 'system_libraries', 'size_limit', 'forbidden_options', 'forbidden_words'):
        if key not in lock:
            raise Failure(f'{path.name}: no {key}')
    ffmpeg = lock['ffmpeg']
    if not re.fullmatch(r'\d+\.\d+\.\d+-\d+', lock['id']) or not lock['id'].startswith(ffmpeg['version'] + '-'):
        raise Failure(f'{path.name}: the id {lock["id"]!r} is not <FFmpeg version>-<build>')
    if ffmpeg['tag'] != f'n{ffmpeg["version"]}' or not re.fullmatch(r'[0-9a-f]{40}', ffmpeg['commit']):
        raise Failure(f'{path.name}: FFmpeg needs the tag n<version> and a full commit')
    for entry in [ffmpeg, *lock['sources']]:
        name = entry.get('name', 'ffmpeg')
        if not entry.get('url', '').startswith('https://') or not re.fullmatch(r'[0-9a-f]{64}', entry.get('sha256', '')):
            raise Failure(f'{path.name}: {name} has no https address or SHA-256')
        if not isinstance(entry.get('size'), int) or entry['size'] <= 0:
            raise Failure(f'{path.name}: {name} has no size')
        if 'commit' in entry and not re.fullmatch(r'[0-9a-f]{40}', entry['commit']):
            raise Failure(f'{path.name}: {name}: the commit is not a full commit')
    for system in ('windows-x64', 'linux-x64'):
        if not re.fullmatch(r'sha256:[0-9a-f]{64}', lock['containers'][system]['digest']):
            raise Failure(f'{path.name}: the container of {system} is not pinned by its digest')
    for option in lock['configure']['common']:
        if option in lock['forbidden_options']:
            raise Failure(f'{path.name}: {option} is in the configure options')
    return lock


def source_entries(lock: dict, system: str | None = None) -> list:
    """The ffmpeg entry (named "ffmpeg") and every source of SYSTEM, or of every system"""
    entries = [{**lock['ffmpeg'], 'name': 'ffmpeg', 'systems': list(SYSTEMS)}]
    entries += [entry for entry in lock['sources'] if system is None or system in entry['systems']]
    return entries


def archive_name(lock: dict, system: str) -> str:
    return f'Immuch360-ffmpeg-{lock["id"]}-{system}.zip'


def wanted(lock: dict, kind: str, system: str) -> list:
    """The components of KIND the lock asks configure for on SYSTEM"""
    table = lock['components'].get(kind, {})
    return sorted(set(table.get('all', [])) | set(table.get(system, [])))


def expected(lock: dict, kind: str, system: str) -> list:
    """The components of KIND configure must enable on SYSTEM: those asked, and those it pulls in"""
    return sorted(set(wanted(lock, kind, system)) | set(lock['pulled'].get(kind, [])))


def printed(lock: dict, kind: str, system: str) -> list:
    """The names the program prints for KIND on SYSTEM"""
    names = [lock['printed'].get(kind, {}).get(name, name) for name in expected(lock, kind, system)]
    if kind == 'demuxer':
        names += [lock['printed'].get('indev', {}).get(name, name) for name in expected(lock, 'indev', system)]
    if kind == 'filter':
        names += lock['printed']['filter_always']
    return sorted(set(names))


def configure_options(lock: dict, system: str) -> list:
    """The configure options of the lock for SYSTEM, the components included, in a fixed order"""
    options = [*lock['configure']['common'], *lock['configure'][system]]
    for kind in KINDS:
        names = wanted(lock, kind, system)
        if names:
            options.append(f'--enable-{kind}={",".join(names)}')
    return options


def command_lock(args) -> int:
    lock = load_lock(args.lock)
    container = lock['containers'][args.system]
    values = {
        'id': lock['id'],
        'version': lock['ffmpeg']['version'],
        'artifact': archive_name(lock, args.system),
        'image': f'{container["image"].split(":")[0]}@{container["digest"]}' if 'digest' in container else '',
        'xcode': container.get('xcode', ''),
        # The lines of sources.list (";" between them) and the packages, for the container's first step, which has
        # no Python yet
        'apt_sources': ';'.join(f'deb [check-valid-until=no] {line}' for line in container.get('apt', [])),
        'packages': ' '.join(container.get('packages', container.get('brew', []))),
    }
    for key, value in values.items():
        print(f'{key}={value}')
    if args.github_output:
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as stream:
            for key, value in values.items():
                stream.write(f'{key}={value}\n')
    return 0


# --- helpers -----------------------------------------------------------------------------------------------------

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with open(path, 'rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            digest.update(block)
    return digest.hexdigest()


def text_bytes(data: bytes) -> bytes:
    """A text as compared: LF line ends (a checkout on Windows may give CRLF)"""
    return data.replace(b'\r\n', b'\n')


def run(command: list, cwd: pathlib.Path | None = None, env: dict | None = None):
    print('$ ' + ' '.join(shlex.quote(str(part)) for part in command), flush=True)
    subprocess.run([str(part) for part in command], cwd=cwd, check=True, env=env)


def output(command: list, cwd: pathlib.Path | None = None, env: dict | None = None) -> str:
    return subprocess.run([str(part) for part in command], cwd=cwd, check=True, capture_output=True, text=True,
                          env=env).stdout.strip()


def first_line(command: list) -> str:
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=60)
    except OSError as error:
        return f'not found ({error})'
    text = (result.stdout or result.stderr).strip()
    return text.splitlines()[0] if text else ''


def download(url: str, target: pathlib.Path):
    for attempt in range(1, 4):
        try:
            request = urllib.request.Request(url, headers={'User-Agent': 'immuch360-ffmpeg-build'})
            with urllib.request.urlopen(request, timeout=300) as response, open(target, 'wb') as stream:
                shutil.copyfileobj(response, stream)
            return
        except OSError as error:
            if attempt == 3:
                raise Failure(f'{url}: {error}') from None
            print(f'{url}: {error}, trying again', flush=True)
            time.sleep(10 * attempt)


def file_name(entry: dict) -> str:
    return entry['url'].rsplit('/', 1)[1]


# --- sources -----------------------------------------------------------------------------------------------------

def unpack(archive: pathlib.Path, target: pathlib.Path):
    """An archive unpacked without its top folder, its members kept inside target"""
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    with tarfile.open(archive) as bundle:
        members = bundle.getmembers()
        tops = {member.name.split('/', 1)[0] for member in members}
        if len(tops) != 1:
            raise Failure(f'{archive.name}: not one top folder ({sorted(tops)[:5]})')
        for member in members:
            parts = member.name.split('/', 1)
            if len(parts) < 2 or not parts[1]:
                continue
            member.name = parts[1]
            relative = pathlib.PurePosixPath(member.name)
            if relative.is_absolute() or '..' in relative.parts:
                raise Failure(f'{archive.name}: unsafe path {member.name}')
            if member.islnk() or member.issym():
                link = pathlib.PurePosixPath(member.linkname)
                if link.is_absolute() or '..' in link.parts and member.issym() and \
                        '..' in pathlib.PurePosixPath(relative.parent, link).parts[:1]:
                    raise Failure(f'{archive.name}: unsafe link {member.name}')
                if member.islnk():
                    member.linkname = member.linkname.split('/', 1)[1]
            if hasattr(tarfile, 'data_filter'):
                bundle.extract(member, target, filter='fully_trusted')
            else:
                bundle.extract(member, target)


def closure(configure: str, start: set) -> set:
    """Every name reached from START through the _select lines of FFmpeg's configure"""
    selects = {match.group(1): match.group(2).split()
               for match in re.finditer(r'^(\w+)_select="([^"]*)"', configure, re.MULTILINE)}
    seen, pending = set(), list(start)
    while pending:
        name = pending.pop()
        if name not in seen:
            seen.add(name)
            pending.extend(selects.get(name, []))
    return seen


def known_components(source: pathlib.Path) -> dict:
    """The components FFmpeg's sources define, by kind (the lists configure builds them from)"""
    patterns = {
        'encoder': ('libavcodec/allcodecs.c', r'extern const FFCodec ff_(\w+)_encoder;'),
        'decoder': ('libavcodec/allcodecs.c', r'extern const FFCodec ff_(\w+)_decoder;'),
        'parser': ('libavcodec/parsers.c', r'extern const FFCodecParser ff_(\w+)_parser;'),
        'bsf': ('libavcodec/bitstream_filters.c', r'extern const FFBitStreamFilter ff_(\w+)_bsf;'),
        'demuxer': ('libavformat/allformats.c', r'extern const FFInputFormat +ff_(\w+)_demuxer;'),
        'muxer': ('libavformat/allformats.c', r'extern const FFOutputFormat ff_(\w+)_muxer;'),
        'filter': ('libavfilter/allfilters.c', r'extern const FFFilter ff_[avs]{1,2}(?:src|sink|f)?_(\w+);'),
        'protocol': ('libavformat/protocols.c', r'extern const URLProtocol ff_(\w+)_protocol;'),
        'indev': ('libavdevice/alldevices.c', r'extern const FFInputFormat +ff_(\w+)_demuxer;'),
    }
    found = {}
    for kind, (path, pattern) in patterns.items():
        found[kind] = set(re.findall(pattern, (source / path).read_text(encoding='utf-8', errors='replace')))
    return found


def pulled_problems(lock: dict, source: pathlib.Path) -> list:
    """Whether the pulled lists of the lock are what configure's _select lines add to the lists asked, on every system"""
    configure = (source / 'configure').read_text(encoding='utf-8', errors='replace')
    known = known_components(source)
    problems = []
    for kind in KINDS:
        for name in sorted(set(lock['components'].get(kind, {}).get('all', [])) |
                           {n for s in SYSTEMS for n in lock['components'].get(kind, {}).get(s, [])}):
            if name not in known[kind]:
                problems.append(f'the lock asks for the {kind} {name}, which FFmpeg {lock["ffmpeg"]["version"]} '
                                'does not have')
    for system in SYSTEMS:
        start = {f'{name}_{kind}' for kind in KINDS for name in wanted(lock, kind, system)}
        start |= set(re.search(r'^ffmpeg_select="([^"]*)"', configure, re.MULTILINE).group(1).split())
        start |= set(re.search(r'^ffprobe_select="([^"]*)"', configure, re.MULTILINE).group(1).split()) \
            if re.search(r'^ffprobe_select="', configure, re.MULTILINE) else set()
        reached = closure(configure, start)
        for kind in KINDS:
            names = {item[:-len(kind) - 1] for item in reached if item.endswith(f'_{kind}')} & known[kind]
            extra = sorted(names - set(wanted(lock, kind, system)))
            if extra != sorted(lock['pulled'].get(kind, [])):
                problems.append(f'{system}: configure pulls the {kind}s {extra}, the lock says '
                                f'{sorted(lock["pulled"].get(kind, []))}')
    return problems


def command_sources(args) -> int:
    lock = load_lock(args.lock)
    cache = args.cache or args.dir / 'archives'
    cache.mkdir(parents=True, exist_ok=True)
    for entry in source_entries(lock, args.system):
        path = cache / file_name(entry)
        if not path.is_file() or sha256_file(path) != entry['sha256']:
            print(f'{entry["name"]}: {entry["url"]}', flush=True)
            download(entry['url'], path)
        size, digest = path.stat().st_size, sha256_file(path)
        if size != entry['size'] or digest != entry['sha256']:
            raise Failure(f'{path.name}: {size} bytes, SHA-256 {digest}; the lock says {entry["size"]} bytes, '
                          f'{entry["sha256"]}')
        target = args.dir / entry['name']
        if entry.get('file'):
            target.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target / path.name)
        else:
            unpack(path, target)
        print(f'{entry["name"]} {entry["version"]}: {size} bytes, SHA-256 checked, in {target}', flush=True)
    release = (args.dir / 'ffmpeg' / 'RELEASE').read_text(encoding='utf-8').strip()
    if release != lock['ffmpeg']['version']:
        raise Failure(f'FFmpeg RELEASE says {release}, the lock says {lock["ffmpeg"]["version"]}')
    problems = pulled_problems(lock, args.dir / 'ffmpeg')
    for problem in problems:
        print(f'::error::{problem}')
    return 1 if problems else 0


# --- build -------------------------------------------------------------------------------------------------------

class Builder:
    """The build of one architecture: the libraries in work/<arch>/deps, FFmpeg in work/<arch>/ffmpeg"""

    def __init__(self, system: str, arch: str, src: pathlib.Path, work: pathlib.Path, jobs: int, lock: dict):
        self.system, self.arch, self.src, self.lock = system, arch, src, lock
        self.root = work / arch
        self.deps = self.root / 'deps'
        self.jobs = str(jobs)
        self.work = work
        minimum = lock['containers']['macos-universal']['minimum']
        maps = f'-ffile-prefix-map={src}=/src -ffile-prefix-map={work}=/build'
        if system == 'macos-universal':
            self.arch_flags = f'-arch {arch} -mmacosx-version-min={minimum}'
            self.host = 'aarch64-apple-darwin' if arch == 'arm64' else 'x86_64-apple-darwin'
            self.cc, self.cxx = f'clang {self.arch_flags}', f'clang++ {self.arch_flags}'
        elif system == 'windows-x64':
            self.arch_flags = ''
            self.host = 'x86_64-w64-mingw32'
            self.cc, self.cxx = 'x86_64-w64-mingw32-gcc', 'x86_64-w64-mingw32-g++'
        else:
            self.arch_flags = ''
            self.host = 'x86_64-linux-gnu'
            self.cc, self.cxx = 'gcc', 'g++'
        self.cflags = f'-O2 {"-fPIC " if system == "linux-x64" else ""}{maps} {self.arch_flags}'.strip()
        self.ldflags = self.arch_flags
        if system == 'windows-x64':
            # No time stamp in the PE headers, so that two builds give the same bytes
            self.ldflags = '-static-libgcc -static-libstdc++ -Wl,--no-insert-timestamp'

    def env(self) -> dict:
        env = dict(os.environ)
        env['PKG_CONFIG_LIBDIR'] = str(self.deps / 'lib' / 'pkgconfig')
        if self.system == 'linux-x64':
            # The libdrm of the build container, which libva-drm needs (the computer's at run time); the libraries of
            # this build come first
            env['PKG_CONFIG_LIBDIR'] += ':/usr/lib/x86_64-linux-gnu/pkgconfig:/usr/share/pkgconfig'
        env.pop('PKG_CONFIG_PATH', None)
        env['LC_ALL'] = 'C'
        env['TZ'] = 'UTC'
        return env

    def copy(self, name: str) -> pathlib.Path:
        folder = self.root / 'build' / name
        if folder.exists():
            shutil.rmtree(folder)
        shutil.copytree(self.src / name, folder, symlinks=True)
        return folder

    def zlib(self):
        folder = self.copy('zlib')
        env = self.env()
        if self.system == 'windows-x64':
            run(['make', '-f', 'win32/Makefile.gcc', f'-j{self.jobs}', 'PREFIX=x86_64-w64-mingw32-',
                 f'CFLAGS={self.cflags} -Wall', 'libz.a'], cwd=folder, env=env)
            (self.deps / 'include').mkdir(parents=True, exist_ok=True)
            (self.deps / 'lib' / 'pkgconfig').mkdir(parents=True, exist_ok=True)
            for header in ('zlib.h', 'zconf.h'):
                shutil.copyfile(folder / header, self.deps / 'include' / header)
            shutil.copyfile(folder / 'libz.a', self.deps / 'lib' / 'libz.a')
            version = next(entry for entry in self.lock['sources'] if entry['name'] == 'zlib')['version']
            (self.deps / 'lib' / 'pkgconfig' / 'zlib.pc').write_text('\n'.join([
                f'prefix={self.deps}', 'libdir=${prefix}/lib', 'includedir=${prefix}/include', '', 'Name: zlib',
                'Description: zlib compression library', f'Version: {version}', 'Libs: -L${libdir} -lz',
                'Cflags: -I${includedir}', '']), encoding='utf-8')
        else:
            env.update(CC=self.cc, CFLAGS=self.cflags)
            run(['./configure', '--static', f'--prefix={self.deps}'], cwd=folder, env=env)
            run(['make', f'-j{self.jobs}', 'install'], cwd=folder, env=env)

    def zimg(self):
        folder = self.copy('zimg')
        env = self.env()
        env.update(CC=self.cc, CXX=self.cxx, CFLAGS=self.cflags, CXXFLAGS=self.cflags, LDFLAGS=self.ldflags)
        # The C++ library, and on Linux the maths library, which the static libzimg needs (its zimg.pc says so)
        env['STL_LIBS'] = '-lc++' if self.system == 'macos-universal' else '-lstdc++ -lm'
        run(['sh', './autogen.sh'], cwd=folder, env=env)
        configure = ['./configure', f'--prefix={self.deps}', '--disable-shared', '--enable-static', '--with-pic',
                     f'--host={self.host}']
        run(configure, cwd=folder, env=env)
        run(['make', f'-j{self.jobs}'], cwd=folder, env=env)
        run(['make', 'install'], cwd=folder, env=env)

    def cmake_system(self) -> list:
        if self.system == 'windows-x64':
            return ['-DCMAKE_SYSTEM_NAME=Windows', '-DCMAKE_SYSTEM_PROCESSOR=AMD64',
                    f'-DCMAKE_C_COMPILER={self.cc}', f'-DCMAKE_CXX_COMPILER={self.cxx}',
                    '-DCMAKE_RC_COMPILER=x86_64-w64-mingw32-windres', '-DCMAKE_FIND_ROOT_PATH=/usr/x86_64-w64-mingw32',
                    '-DCMAKE_FIND_ROOT_PATH_MODE_PROGRAM=NEVER',
                    '-DCMAKE_FIND_ROOT_PATH_MODE_LIBRARY=ONLY', '-DCMAKE_FIND_ROOT_PATH_MODE_INCLUDE=ONLY']
        if self.system == 'macos-universal':
            minimum = self.lock['containers']['macos-universal']['minimum']
            extra = [f'-DCMAKE_OSX_ARCHITECTURES={self.arch}', f'-DCMAKE_OSX_DEPLOYMENT_TARGET={minimum}']
            if self.arch != platform.machine():
                extra += ['-DCMAKE_SYSTEM_NAME=Darwin', f'-DCMAKE_SYSTEM_PROCESSOR={self.arch}']
            return extra
        return []

    def svt_av1(self):
        folder = self.copy('svt-av1')
        build = folder / 'immuch360-build'
        flags = self.cflags.replace(self.arch_flags, '').strip()
        options = ['-G', 'Ninja', '-DCMAKE_BUILD_TYPE=Release', '-DBUILD_SHARED_LIBS=OFF', '-DBUILD_APPS=OFF',
                   '-DBUILD_TESTING=OFF', '-DREPRODUCIBLE_BUILDS=ON', '-DEXCLUDE_HASH=ON', '-DSVT_AV1_LTO=OFF',
                   '-DNATIVE=OFF', '-DCMAKE_POSITION_INDEPENDENT_CODE=ON', f'-DCMAKE_INSTALL_PREFIX={self.deps}',
                   '-DCMAKE_INSTALL_LIBDIR=lib', f'-DCMAKE_C_FLAGS={flags}', f'-DCMAKE_CXX_FLAGS={flags}']
        if self.system == 'macos-universal' and self.arch == 'arm64':
            # No Apple processor has SVE
            options += ['-DENABLE_SVE=OFF', '-DENABLE_SVE2=OFF']
        run(['cmake', '-S', folder, '-B', build, *options, *self.cmake_system()], env=self.env())
        run(['cmake', '--build', build, '-j', self.jobs], env=self.env())
        run(['cmake', '--install', build], env=self.env())

    def meson_file(self) -> list:
        """The cross file of meson for a cross build, the native file otherwise"""
        path = self.root / 'meson.ini'
        args = ', '.join(f"'{part}'" for part in shlex.split(self.cflags))
        if self.system == 'windows-x64':
            path.write_text('\n'.join([
                '[binaries]', f"c = '{self.cc}'", f"cpp = '{self.cxx}'", "ar = 'x86_64-w64-mingw32-ar'",
                "strip = 'x86_64-w64-mingw32-strip'", "windres = 'x86_64-w64-mingw32-windres'",
                "pkg-config = 'pkg-config'", "nasm = 'nasm'", '', '[built-in options]', f'c_args = [{args}]',
                "c_link_args = ['-Wl,--no-insert-timestamp']", '', '[host_machine]', "system = 'windows'",
                "cpu_family = 'x86_64'", "cpu = 'x86_64'", "endian = 'little'", '']), encoding='utf-8')
            return ['--cross-file', path]
        if self.system == 'macos-universal':
            cross = self.arch != platform.machine()
            arch = "'-arch', '" + self.arch + "'"
            lines = ['[binaries]', f"c = ['clang', {arch}]", f"cpp = ['clang++', {arch}]", "ar = 'ar'",
                     "strip = 'strip'", "nasm = 'nasm'", "pkg-config = 'pkg-config'", '', '[built-in options]',
                     f'c_args = [{args}]', f"c_link_args = [{arch}, '-mmacosx-version-min="
                     f"{self.lock['containers']['macos-universal']['minimum']}']", '']
            if cross:
                lines += ['[host_machine]', "system = 'darwin'", "cpu_family = 'x86_64'", "cpu = 'x86_64'",
                          "endian = 'little'", '']
            path.write_text('\n'.join(lines), encoding='utf-8')
            return ['--cross-file' if cross else '--native-file', path]
        path.write_text('\n'.join(['[built-in options]', f'c_args = [{args}]', '']), encoding='utf-8')
        return ['--native-file', path]

    def dav1d(self):
        folder = self.copy('dav1d')
        build = folder / 'immuch360-build'
        run(['meson', 'setup', build, folder, *self.meson_file(), f'--prefix={self.deps}', '--libdir=lib',
             '--buildtype=release', '--default-library=static', '-Db_staticpic=true', '-Denable_tools=false',
             '-Denable_tests=false', '-Denable_examples=false', '-Denable_docs=false'], env=self.env())
        run(['meson', 'compile', '-C', build, '-j', self.jobs], env=self.env())
        run(['meson', 'install', '-C', build], env=self.env())

    def libva(self):
        folder = self.copy('libva')
        build = folder / 'immuch360-build'
        entry = next(entry for entry in self.lock['sources'] if entry['name'] == 'libva')
        env = self.env()
        run(['meson', 'setup', build, folder, *self.meson_file(), f'--prefix={self.deps}', '--libdir=lib',
             '--buildtype=release', f'-Ddriverdir={entry["driverdir"]}', '-Dwith_x11=no', '-Dwith_glx=no',
             '-Dwith_wayland=no', '-Ddisable_drm=false', '-Denable_docs=false'], env=env)
        run(['meson', 'compile', '-C', build, '-j', self.jobs], env=env)
        run(['meson', 'install', '-C', build], env=env)

    def nasm(self) -> pathlib.Path:
        tools = self.work / 'tools'
        if (tools / 'nasm').is_file():
            return tools
        folder = self.work / 'nasm-build'
        if folder.exists():
            shutil.rmtree(folder)
        shutil.copytree(self.src / 'nasm', folder, symlinks=True)
        env = dict(os.environ)
        for key in ('CC', 'CFLAGS', 'LDFLAGS'):
            env.pop(key, None)
        run(['./configure', '--quiet'], cwd=folder, env=env)
        run(['make', f'-j{self.jobs}', 'nasm'], cwd=folder, env=env)
        tools.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(folder / 'nasm', tools / 'nasm')
        (tools / 'nasm').chmod(0o755)
        return tools

    def ffmpeg_configure(self) -> list:
        options = configure_options(self.lock, self.system)
        options = [f'--prefix={PREFIX}', *options]
        cflags = self.cflags
        if self.system == 'windows-x64':
            options += ['--enable-cross-compile', '--cross-prefix=x86_64-w64-mingw32-', '--target-os=mingw32',
                        '--arch=x86_64', '--pkg-config=pkg-config', '--extra-libs=-lwinpthread']
        elif self.system == 'macos-universal':
            options += [f'--arch={self.arch}', '--install-name-dir=@loader_path/../lib', '--cc=clang', '--cxx=clang++',
                        f'--extra-cxxflags={self.arch_flags}']
            if self.arch != platform.machine():
                options += ['--enable-cross-compile', '--target-os=darwin']
        options += [f'--extra-cflags={cflags}', f'--extra-ldflags={self.ldflags}'] if self.ldflags else \
            [f'--extra-cflags={cflags}']
        return options

    def ffmpeg(self) -> dict:
        build = self.root / 'ffmpeg'
        if build.exists():
            shutil.rmtree(build)
        build.mkdir(parents=True)
        options = self.ffmpeg_configure()
        run([self.src / 'ffmpeg' / 'configure', *options], cwd=build, env=self.env())
        flags = config_flags((build / 'config.h').read_text(encoding='utf-8'))
        components = enabled_components(build)
        run(['make', f'-j{self.jobs}'], cwd=build, env=self.env())
        install = self.root / 'install'
        if install.exists():
            shutil.rmtree(install)
        run(['make', 'install', f'DESTDIR={install}'], cwd=build, env=self.env())
        return {'configure': options, 'config_h': flags, 'components': components,
                'install': str(install / PREFIX.lstrip('/'))}

    def all(self) -> dict:
        os.environ['PATH'] = f'{self.nasm()}{os.pathsep}{os.environ["PATH"]}'
        if self.deps.exists():
            shutil.rmtree(self.deps)
        self.zlib()
        self.zimg()
        self.svt_av1()
        self.dav1d()
        if self.system == 'linux-x64':
            self.libva()
        return self.ffmpeg()


def config_flags(text: str) -> dict:
    flags = {}
    for name in CONFIG_FLAGS:
        match = re.search(rf'^#define {name} (\d+)$', text, re.MULTILINE)
        flags[name] = int(match.group(1)) if match else None
    return flags


def enabled_components(build: pathlib.Path) -> dict:
    """The components configure enabled, read from the lists it generated"""
    found = {}
    for kind, path in LIST_FILES.items():
        text = (build / path).read_text(encoding='utf-8')
        if kind == 'filter':
            names = re.findall(r'&ff_[avs]{1,2}(?:src|sink|f)?_(\w+),', text)
            names = [name for name in names if name not in ('abuffer', 'buffer', 'abuffersink', 'buffersink')]
        elif kind == 'indev':
            names = re.findall(r'&ff_(\w+)_demuxer,', text)
        else:
            names = re.findall(rf'&ff_(\w+)_{kind},', text)
        found[kind] = sorted(set(names))
    return found


def build_problems(lock: dict, system: str, result: dict) -> list:
    problems = []
    for name, value in result['config_h'].items():
        if value != 0:
            problems.append(f'config.h: {name} is {value}, not 0')
    for kind in KINDS:
        if result['components'][kind] != expected(lock, kind, system):
            problems.append(f'configure enabled the {kind}s {result["components"][kind]}, the lock says '
                            f'{expected(lock, kind, system)}')
    return problems


def tool_versions(system: str) -> dict:
    if system == 'windows-x64':
        compiler = first_line(['x86_64-w64-mingw32-gcc', '--version'])
    elif system == 'macos-universal':
        compiler = first_line(['clang', '--version'])
    else:
        compiler = first_line(['gcc', '--version'])
    tools = {'compiler': compiler, 'nasm': first_line(['nasm', '-v']), 'cmake': first_line(['cmake', '--version']),
             'meson': first_line(['meson', '--version']), 'ninja': first_line(['ninja', '--version']),
             'make': first_line(['make', '--version']), 'autoconf': first_line(['autoconf', '--version']),
             'pkg-config': first_line(['pkg-config', '--version'])}
    if system == 'macos-universal':
        tools['xcode'] = ' '.join(output(['xcodebuild', '-version']).split())
    if system == 'windows-x64':
        tools['binutils'] = first_line(['x86_64-w64-mingw32-ld', '--version'])
    return tools


def strip_file(system: str, path: pathlib.Path):
    if system == 'windows-x64':
        run(['x86_64-w64-mingw32-strip', '--strip-unneeded', path])
    elif system == 'linux-x64':
        run(['strip', '--strip-unneeded', path])
    else:
        run(['strip', '-x', path])


def stage_linux(result: dict, builder: Builder, stage: pathlib.Path, src: pathlib.Path):
    install = pathlib.Path(result['install'])
    (stage / 'bin').mkdir(parents=True)
    (stage / 'lib').mkdir()
    for program in ('ffmpeg', 'ffprobe'):
        shutil.copyfile(install / 'bin' / program, stage / 'bin' / program)
    libraries = sorted(install.glob('lib/lib*.so.*')) + sorted(builder.deps.glob('lib/libva*.so.*'))
    for library in libraries:
        if library.is_symlink() or not library.is_file():
            continue
        soname = soname_of(library.read_bytes())
        if soname and not (stage / 'lib' / soname).exists():
            shutil.copyfile(library, stage / 'lib' / soname)
    for path in sorted((stage / 'bin').iterdir()) + sorted((stage / 'lib').iterdir()):
        strip_file('linux-x64', path)
        run(['patchelf', '--set-rpath', '$ORIGIN/../lib' if path.parent.name == 'bin' else '$ORIGIN', path])
    launcher = src / 'immuch360-run' / 'immuch360_run.c'
    run(['gcc', '-O2', '-Wall', '-Wextra', '-Werror', f'-ffile-prefix-map={src}=/src', '-o',
         stage / 'bin' / 'immuch360-run', launcher])
    strip_file('linux-x64', stage / 'bin' / 'immuch360-run')


def stage_windows(result: dict, stage: pathlib.Path):
    install = pathlib.Path(result['install'])
    (stage / 'bin').mkdir(parents=True)
    for path in sorted(install.glob('bin/*')):
        if path.suffix.lower() in ('.exe', '.dll'):
            shutil.copyfile(path, stage / 'bin' / path.name)
            strip_file('windows-x64', stage / 'bin' / path.name)


def stage_macos(results: dict, stage: pathlib.Path):
    """Each program and library of the two architectures joined by lipo, then signed ad hoc"""
    (stage / 'bin').mkdir(parents=True)
    (stage / 'lib').mkdir()
    installs = {arch: pathlib.Path(result['install']) for arch, result in results.items()}
    names = [f'bin/{program}' for program in ('ffmpeg', 'ffprobe')]
    first = installs['arm64']
    for library in sorted(first.glob('lib/lib*.dylib')):
        # libavcodec.63.dylib, the install name; not libavcodec.dylib nor libavcodec.63.x.y.dylib
        if re.fullmatch(r'lib\w+\.\d+\.dylib', library.name):
            names.append(f'lib/{library.name}')
    for name in names:
        slices = []
        for arch, install in installs.items():
            path = install / name
            real = path.resolve()
            if not real.is_file():
                raise Failure(f'no {name} in the {arch} build')
            thin = stage.parent / f'thin-{arch}' / name
            thin.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(real, thin)
            strip_file('macos-universal', thin)
            slices.append(thin)
        run(['lipo', '-create', '-output', stage / name, *slices])
        run(['codesign', '--force', '--sign', '-', '--timestamp=none', stage / name])
        run(['codesign', '--verify', '--verbose', stage / name])
    run(['lipo', '-info', stage / 'bin' / 'ffmpeg'])


def command_build(args) -> int:
    lock = load_lock(args.lock)
    work, src = args.work.resolve(), args.src.resolve()
    work.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    arches = ['arm64', 'x86_64'] if args.system == 'macos-universal' else ['x86_64']
    results = {}
    for arch in arches:
        builder = Builder(args.system, arch, src, work, args.jobs or os.cpu_count() or 2, lock)
        results[arch] = builder.all()
    stage = work / 'stage'
    if stage.exists():
        shutil.rmtree(stage)
    if args.system == 'linux-x64':
        stage_linux(results['x86_64'], builder, stage, src)
    elif args.system == 'windows-x64':
        stage_windows(results['x86_64'], stage)
    else:
        stage_macos(results, stage)
    problems = []
    for arch, result in results.items():
        problems += [f'{arch}: {problem}' for problem in build_problems(lock, args.system, result)]
    record = {
        'system': args.system,
        'lock': lock['id'],
        'seconds': round(time.monotonic() - started),
        'tools': tool_versions(args.system),
        'architectures': {arch: {'configure': result['configure'], 'config_h': result['config_h'],
                                 'components': result['components']} for arch, result in results.items()},
        'source_date_epoch': os.environ.get('SOURCE_DATE_EPOCH', ''),
        'container': os.environ.get('IMMUCH360_CONTAINER', ''),
    }
    (work / 'build.json').write_text(json.dumps(record, indent=1) + '\n', encoding='utf-8')
    total = sum(path.stat().st_size for path in stage.rglob('*') if path.is_file())
    print(f'{args.system}: {total} bytes in {stage}, built in {record["seconds"]} s', flush=True)
    for problem in problems:
        print(f'::error::{problem}')
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as stream:
            stream.write(f'seconds={record["seconds"]}\nbytes={total}\n')
    return 1 if problems else 0


# --- licences ----------------------------------------------------------------------------------------------------

def source_text(src: pathlib.Path, entry: dict, lock: dict) -> bytes:
    folder = src / entry['source']
    if entry['path']:
        data = text_bytes((folder / entry['path']).read_bytes())
    else:
        source = next(item for item in lock['sources'] if item['name'] == entry['source'])
        data = text_bytes((folder / file_name(source)).read_bytes())
    if entry.get('lines'):
        first, last = entry['lines']
        data = b''.join(data.splitlines(keepends=True)[first - 1:last])
    return data


def licence_problems(lock: dict, src: pathlib.Path | None, licences: pathlib.Path = LICENCES,
                     system: str | None = None) -> list:
    """What is wrong with the licence texts; with [src], each compared with its source (of [system] only when given,
    whose sources alone are unpacked there)"""
    problems = []
    permissive = set(lock['permissive'])
    named = {entry['text'] for entry in lock['licences']}
    for entry in lock['licences']:
        if entry['licence'] not in permissive or re.search(r'(?<!L)GPL', entry['licence']):
            problems.append(f'{entry["text"]}: {entry["licence"]} is not a licence the lock allows')
        text = licences / entry['text']
        if not text.is_file():
            problems.append(f'no licenses/{entry["text"]}')
            continue
        if src is not None and (system is None or system in entry.get('systems', SYSTEMS)):
            if text_bytes(text.read_bytes()) != source_text(src, entry, lock):
                problems.append(f'licenses/{entry["text"]} differs from {entry["path"] or "the file"} of '
                                f'{entry["source"]}: copy it again')
    for path in sorted(licences.iterdir()):
        if path.name not in named and path.name not in OWN_TEXTS:
            problems.append(f'licenses/{path.name}: a text the lock does not name')
    for name in OWN_TEXTS:
        if not (licences / name).is_file():
            problems.append(f'no licenses/{name}')
    for source in lock['sources']:
        for part in re.split(r'\s+AND\s+', source['licence']):
            if part not in permissive:
                problems.append(f'{source["name"]}: {part} is not a licence the lock allows')
    if src is not None:
        problems += notice_problems(lock, src, licences, system)
    return problems


# The words of the licence grants a header may hold, by kind
GRANTS = {
    'MIT': re.compile(rb'Permission is hereby granted, free of charge'),
    'ISC': re.compile(rb'Permission to use, copy, modify, and(?:/or)? distribute'),
    'BSD': re.compile(rb'Redistribution and use in source and binary forms'),
}
CODE_SUFFIXES = ('.c', '.cc', '.cpp', '.h', '.hpp', '.asm', '.S', '.inc')
# The header of a file: where its notice is
HEADER_BYTES = 8192
COPYRIGHT_LINE = re.compile(r'Copyright\s*(?:\([cC]\)|©)?\s*(?:[0-9]{4}(?:\s*[-,]\s*[0-9]{4})*\s*,?)?\s*(.+)')


def grant_kinds(header: bytes) -> set:
    """The kinds of licence grant a header holds"""
    return {kind for kind, words in GRANTS.items() if words.search(header)}


def copyright_holders(header: bytes) -> list:
    """The holders of the Copyright lines of a header, without the years and "All rights reserved\""""
    holders = []
    for line in header.decode('utf-8', 'replace').splitlines():
        found = COPYRIGHT_LINE.search(line)
        if not found:
            continue
        holder = re.sub(r'\s*All rights reserved\.?\s*$', '', found.group(1).strip(), flags=re.IGNORECASE)
        holder = holder.strip(' .,;*/')
        if holder and not holder.lower().startswith(('notice', 'holder')):
            holders.append(holder)
    return holders


def notice_problems(lock: dict, src: pathlib.Path, licences: pathlib.Path = LICENCES,
                    system: str | None = None) -> list:
    """The files compiled into the program (sources.lock, notice_scan) whose header grants a licence of another kind
    than their library's and that no text of licenses/ covers, or whose copyright holders that text does not name"""
    scan = lock.get('notice_scan')
    if not scan:
        return ['sources.lock has no notice_scan']
    problems = []
    entries = {entry['name']: entry for entry in lock['sources']}
    for name, rule in scan['sources'].items():
        entry = entries.get(name)
        if entry is None:
            problems.append(f'notice_scan: {name} is not a source of the lock')
            continue
        if system is not None and system not in entry.get('systems', SYSTEMS):
            continue
        folder = src / name
        if not folder.is_dir():
            problems.append(f'notice_scan: no {folder}')
            continue
        for path in sorted(folder.rglob('*')):
            if not path.is_file() or path.suffix not in CODE_SUFFIXES:
                continue
            relative = path.relative_to(folder).as_posix()
            if not any(fnmatch.fnmatchcase(relative, glob) for glob in rule['compiled']) or \
                    any(fnmatch.fnmatchcase(relative, glob) for glob in rule.get('not_compiled', [])):
                continue
            with path.open('rb') as handle:
                header = handle.read(HEADER_BYTES)
            other = sorted(grant_kinds(header) - set(rule['kinds']))
            if not other:
                continue
            cover = next((item for item in scan['covered'] if item['source'] == name and
                          any(fnmatch.fnmatchcase(relative, glob) for glob in item['paths'])), None)
            if cover is None:
                problems.append(f'{name}/{relative}: its {" and ".join(other)} notice is in no text of licenses/ '
                                '(sources.lock, notice_scan)')
                continue
            text_path = licences / cover['text']
            if not text_path.is_file():
                problems.append(f'{name}/{relative}: no licenses/{cover["text"]}')
                continue
            text = text_path.read_bytes().decode('utf-8', 'replace')
            for holder in copyright_holders(header):
                if holder not in text:
                    problems.append(f'{name}/{relative}: licenses/{cover["text"]} does not name {holder!r}')
    return problems


def command_licences(args) -> int:
    lock = load_lock(args.lock)
    problems = licence_problems(lock, args.src)
    for problem in problems:
        print(f'::error::{problem}')
    if not problems:
        print(f'licences: {len(lock["licences"])} texts, each the file of its source' +
              ('' if args.src else ' (not compared: no --src)'))
    return 1 if problems else 0


# --- archive -----------------------------------------------------------------------------------------------------

def is_program(system: str, name: str) -> bool:
    """Whether a file of the archive is a program, executable once unpacked"""
    if system == 'windows-x64':
        return name.endswith('.exe')
    return name.startswith('bin/')


def write_archive(target: pathlib.Path, files: dict, system: str):
    target.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as bundle:
        for name in sorted(files):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (0o100755 if is_program(system, name) else 0o100644) << 16
            info.compress_type = zipfile.ZIP_DEFLATED
            bundle.writestr(info, files[name], compresslevel=9)


def sums_text(files: dict) -> bytes:
    return ''.join(f'{sha256(files[name])}  {name}\n' for name in sorted(files) if name != 'SHA256SUMS.txt').encode()


def licence_files(lock: dict, system: str, licences: pathlib.Path = LICENCES) -> dict:
    files = {}
    for entry in lock['licences']:
        if system in entry.get('systems', SYSTEMS):
            files[f'licenses/{entry["text"]}'] = text_bytes((licences / entry['text']).read_bytes())
    for name in OWN_TEXTS:
        files[f'licenses/{name}'] = text_bytes((licences / name).read_bytes())
    return files


def source_note(lock: dict, tag: str, commit: str, repo: str) -> bytes:
    base = f'https://github.com/{repo}'
    return '\n'.join([
        'The corresponding source of this program (GNU LGPL 2.1, section 6), offered from the same place as the archive:',
        f'{base}/releases/download/{tag}/{tag}-sources.tar.xz',
        '',
        f'It holds FFmpeg {lock["ffmpeg"]["version"]} ({lock["ffmpeg"]["tag"]}, commit {lock["ffmpeg"]["commit"]}), every',
        'library of the archive as its release tarball, the recipe of this build and the exact configure lines.',
        f'Recipe: {base}/tree/{commit}/ffmpeg (sources.lock, build.py) and .github/workflows/ffmpeg.yml',
        f'Release: {base}/releases/tag/{tag}',
        '',
    ]).encode()


def build_info(lock: dict, system: str, record: dict, tag: str, commit: str, repo: str) -> bytes:
    lines = [f'Immuch360 FFmpeg program for {system}, lock {lock["id"]}, release {tag}',
             f'Built by https://github.com/{repo} at {commit}']
    if os.environ.get('GITHUB_RUN_ID'):
        lines.append(f'Run: {os.environ.get("GITHUB_SERVER_URL", "https://github.com")}/{repo}/actions/runs/'
                     f'{os.environ["GITHUB_RUN_ID"]}')
    lines.append(f'FFmpeg {lock["ffmpeg"]["version"]}: {lock["ffmpeg"]["url"]} SHA-256 {lock["ffmpeg"]["sha256"]} '
                 f'(tag {lock["ffmpeg"]["tag"]}, commit {lock["ffmpeg"]["commit"]})')
    for entry in lock['sources']:
        if system in entry['systems']:
            what = ' (build tool)' if entry.get('tool') else ''
            lines.append(f'{entry["name"]} {entry["version"]}{what}: {entry["url"]} SHA-256 {entry["sha256"]}')
    container = lock['containers'][system]
    if 'digest' in container:
        lines.append(f'Container: {container["image"]}@{container["digest"]}, packages of ' +
                     ', '.join(container['apt']))
    else:
        lines.append(f'Runner: {container["runner"]}, Xcode {container["xcode"]}, macOS {container["minimum"]} and '
                     'later')
    for key, value in record['tools'].items():
        lines.append(f'{key}: {value}')
    if record.get('source_date_epoch'):
        lines.append(f'SOURCE_DATE_EPOCH: {record["source_date_epoch"]}')
    for arch, data in record['architectures'].items():
        flags = ', '.join(f'{name} {value}' for name, value in data['config_h'].items())
        lines.append(f'config.h ({arch}): {flags}')
        lines.append(f'configure ({arch}): ' + ' '.join(shlex.quote(option) for option in data['configure']))
    lines.append('Licence: GNU LGPL version 2.1 or later (licenses/README.md)')
    return ('\n'.join(lines) + '\n').encode()


def command_archive(args) -> int:
    lock = load_lock(args.lock)
    work = args.work.resolve()
    record = json.loads((work / 'build.json').read_text(encoding='utf-8'))
    if record['system'] != args.system:
        raise Failure(f'{work / "build.json"} is the build of {record["system"]}')
    problems = licence_problems(lock, args.src, system=args.system)
    stage = work / 'stage'
    files = {}
    for path in sorted(stage.rglob('*')):
        if path.is_file():
            files[path.relative_to(stage).as_posix()] = path.read_bytes()
    files.update(licence_files(lock, args.system))
    for entry in lock.get('runtime_licences', {}).get(args.system, []):
        source = pathlib.Path(entry['from'])
        if not source.is_file():
            problems.append(f'no {source}: the licence text of {entry["what"]}')
            continue
        files[f'licenses/{entry["text"]}'] = text_bytes(source.read_bytes())
    commit = args.commit or os.environ.get('GITHUB_SHA') or 'unknown'
    files[SOURCE_NOTE] = source_note(lock, args.tag, commit, args.repo)
    files['BUILD-INFO.txt'] = build_info(lock, args.system, record, args.tag, commit, args.repo)
    files['SHA256SUMS.txt'] = sums_text(files)
    problems += static_problems(lock, args.system, files)
    for problem in problems:
        print(f'::error::{problem}')
    if problems:
        return 1
    target = args.out / archive_name(lock, args.system)
    write_archive(target, files, args.system)
    for name in sorted(files):
        print(f'{len(files[name]):>10}  {sha256(files[name])}  {name}')
    digest = sha256_file(target)
    print(f'{target.name}: {target.stat().st_size} bytes, SHA-256 {digest}')
    if os.environ.get('GITHUB_OUTPUT'):
        with open(os.environ['GITHUB_OUTPUT'], 'a', encoding='utf-8') as stream:
            stream.write(f'archive={target}\nsha256={digest}\nsize={target.stat().st_size}\n')
    return 0


# --- the programs and libraries: imports, sizes ------------------------------------------------------------------

def elf_dynamic(data: bytes) -> dict:
    """The DT_NEEDED names, the DT_SONAME and the DT_RUNPATH or DT_RPATH of a 64 bit little endian ELF file"""
    if data[:4] != b'\x7fELF' or data[4] != 2 or data[5] != 1:
        raise Failure('not a 64 bit little endian ELF file')
    shoff, = struct.unpack_from('<Q', data, 0x28)
    shentsize, shnum = struct.unpack_from('<HH', data, 0x3A)
    sections = [struct.unpack_from('<IIQQQQIIQQ', data, shoff + index * shentsize) for index in range(shnum)]
    found = {'needed': [], 'soname': None, 'runpath': None}
    for _, kind, _, _, offset, size, link, _, _, entsize in sections:
        if kind != 6:  # SHT_DYNAMIC
            continue
        strings = sections[link]
        for at in range(offset, offset + size, entsize or 16):
            tag, value = struct.unpack_from('<qQ', data, at)
            if tag == 0:
                break
            if tag in (1, 14, 15, 29):
                start = strings[4] + value
                text = data[start:data.index(b'\0', start)].decode()
                if tag == 1:
                    found['needed'].append(text)
                elif tag == 14:
                    found['soname'] = text
                else:
                    found['runpath'] = text
    return found


def soname_of(data: bytes) -> str | None:
    try:
        return elf_dynamic(data)['soname']
    except (Failure, struct.error, ValueError, IndexError):
        return None


MACHO_CPUS = {0x01000007: 'x86_64', 0x0100000C: 'arm64'}
# LC_LOAD_DYLIB, LC_LAZY_LOAD_DYLIB, LC_LOAD_WEAK_DYLIB, LC_REEXPORT_DYLIB, LC_LOAD_UPWARD_DYLIB
MACHO_DYLIB_COMMANDS = {0xC, 0x20, 0x80000018, 0x8000001F, 0x80000023}
MACHO_ID_DYLIB = 0xD


def macho_dylibs(data: bytes) -> dict:
    """{architecture: {'loads': [dylibs], 'id': install name or None}} of a thin or universal 64 bit Mach-O file"""
    slices = []
    magic, = struct.unpack_from('>I', data, 0)
    if magic == 0xCAFEBABE:
        count, = struct.unpack_from('>I', data, 4)
        for index in range(count):
            cpu, _, offset, size, _ = struct.unpack_from('>iiIII', data, 8 + index * 20)
            slices.append(data[offset:offset + size])
    else:
        slices.append(data)
    found = {}
    for thin in slices:
        magic, cputype, _, _, ncmds, _, _, _ = struct.unpack_from('<IiiIIIII', thin, 0)
        if magic != 0xFEEDFACF:
            raise Failure('not a 64 bit Mach-O file')
        arch = MACHO_CPUS.get(cputype & 0xFFFFFFFF, hex(cputype & 0xFFFFFFFF))
        at, loads, ident = 32, [], None
        for _ in range(ncmds):
            command, size = struct.unpack_from('<II', thin, at)
            if command in MACHO_DYLIB_COMMANDS or command == MACHO_ID_DYLIB:
                name_offset, = struct.unpack_from('<I', thin, at + 8)
                start = at + name_offset
                name = thin[start:thin.index(b'\0', start)].decode()
                if command == MACHO_ID_DYLIB:
                    ident = name
                else:
                    loads.append(name)
            at += size
        found[arch] = {'loads': loads, 'id': ident}
    return found


def pe_info(data: bytes) -> dict:
    sys.path.insert(0, str(HERE))
    import pe_imports as reader  # noqa: E402 (the PE reader next to this script)

    return reader.read_pe(data)


def binaries(system: str, files: dict) -> list:
    if system == 'windows-x64':
        return sorted(name for name in files if name.startswith('bin/') and name.endswith(('.exe', '.dll')))
    return sorted(name for name in files if name.startswith(('bin/', 'lib/')))


def own_names(system: str, files: dict) -> set:
    names = set()
    for name in binaries(system, files):
        base = name.rsplit('/', 1)[1]
        if system == 'windows-x64':
            names.add(base.lower())
        elif system == 'linux-x64':
            names.add(base)
        else:
            names.add(f'@loader_path/../lib/{base}')
    return names


def allowed_system(lock: dict, system: str, name: str) -> bool:
    for pattern in lock['system_libraries'][system]:
        if fnmatch.fnmatchcase(name.lower() if system == 'windows-x64' else name, pattern):
            return True
    if system == 'windows-x64' and re.match(r'^(api|ext)-ms-win-', name.lower()):
        return True
    return False


def static_problems(lock: dict, system: str, files: dict) -> list:
    """The programs and libraries of an archive: their imports, their form, their size, their configuration string"""
    problems = []
    own = own_names(system, files)
    programs = ['bin/ffmpeg.exe', 'bin/ffprobe.exe'] if system == 'windows-x64' else ['bin/ffmpeg', 'bin/ffprobe']
    if system == 'linux-x64':
        programs.append('bin/immuch360-run')
    for name in programs:
        if name not in files:
            problems.append(f'no {name} in the archive')
    total = 0
    for name in binaries(system, files):
        data = files[name]
        total += len(data)
        try:
            if system == 'windows-x64':
                info = pe_info(data)
                if info['machine'] != 'x64':
                    problems.append(f'{name} is built for {info["machine"]}, not x64')
                for dll in info['imports'] + info['delay_imports']:
                    if dll.lower() not in own and not allowed_system(lock, system, dll):
                        problems.append(f'{name} imports {dll}: neither a DLL of Windows nor one of the archive')
            elif system == 'linux-x64':
                dynamic = elf_dynamic(data)
                for needed in dynamic['needed']:
                    if needed not in own and not allowed_system(lock, system, needed):
                        problems.append(f'{name} needs {needed}: neither a library of the system nor of the archive')
                want = '$ORIGIN/../lib' if name.startswith('bin/') else '$ORIGIN'
                if dynamic['needed'] and any(n in own for n in dynamic['needed']) and dynamic['runpath'] != want:
                    problems.append(f'{name}: run path {dynamic["runpath"]!r}, not {want}')
            else:
                slices = macho_dylibs(data)
                if sorted(slices) != ['arm64', 'x86_64']:
                    problems.append(f'{name} holds {sorted(slices)}, not arm64 and x86_64')
                for arch, entry in slices.items():
                    for dylib in entry['loads']:
                        if dylib not in own and not allowed_system(lock, system, dylib):
                            problems.append(f'{name} ({arch}) loads {dylib}: neither a library of the system nor '
                                            'of the archive')
                    if name.startswith('lib/') and entry['id'] != f'@loader_path/../lib/{name[4:]}':
                        problems.append(f'{name} ({arch}): install name {entry["id"]!r}')
        except (Failure, struct.error, ValueError, IndexError) as error:
            problems.append(f'{name}: unreadable ({error})')
        # The configure line libavutil keeps (avutil_configuration), and any copy of it
        for at in [match.start() for match in re.finditer(re.escape(CONFIGURATION_START), data)]:
            line = data[at:data.find(b'\0', at)].decode('utf-8', 'replace')
            for option in lock['forbidden_options']:
                if option in line.split():
                    problems.append(f'{name}: its configure line holds {option}')
            for word in lock['forbidden_words']:
                if word in line.lower():
                    problems.append(f'{name}: its configure line names {word}')
    limit = lock['size_limit'][system]
    if total > limit:
        problems.append(f'the programs and libraries take {total} bytes unpacked, over the limit of {limit}')
    return problems


# --- check -------------------------------------------------------------------------------------------------------

def parse_codecs(text: str) -> list:
    names, started = [], False
    for line in text.splitlines():
        if line.strip().startswith('------'):
            started = True
            continue
        if started and line.strip():
            parts = line.split()
            if len(parts) >= 2:
                names.append(parts[1])
    return sorted(set(names))


def parse_formats(text: str) -> list:
    names, started = [], False
    for line in text.splitlines():
        if line.strip() in ('--', '---'):
            started = True
            continue
        match = re.match(r'^ ([D ])([E ])([d ]) (\S+)', line)
        if started and match:
            names.append(match.group(4))
    return sorted(set(names))


def parse_filters(text: str) -> list:
    names, started = [], False
    for line in text.splitlines():
        if line.strip() == '------':
            started = True
            continue
        if started and line.strip():
            parts = line.split()
            if len(parts) >= 2:
                names.append(parts[1])
    return sorted(set(names))


def parse_bsfs(text: str) -> list:
    lines = [line.strip() for line in text.splitlines()]
    if 'Bitstream filters:' not in lines:
        return []
    return sorted({line for line in lines[lines.index('Bitstream filters:') + 1:] if line})


def parse_protocols(text: str) -> dict:
    found, side = {'input': [], 'output': []}, None
    for line in text.splitlines():
        if line.strip() == 'Input:':
            side = 'input'
        elif line.strip() == 'Output:':
            side = 'output'
        elif side and line.startswith('  ') and line.strip():
            found[side].append(line.strip())
    return {key: sorted(value) for key, value in found.items()}


PARSERS = {'encoder': parse_codecs, 'decoder': parse_codecs, 'muxer': parse_formats, 'demuxer': parse_formats,
           'filter': parse_filters, 'bsf': parse_bsfs}


def buildconf_options(text: str) -> list:
    lines = text.replace('\r\n', '\n').split('\n')
    try:
        start = next(index for index, line in enumerate(lines) if line.strip() == 'configuration:')
    except StopIteration:
        return []
    # Options with a value configure quoted keep their quotes there: --enable-encoder='aac,libsvtav1'
    options = []
    for line in lines[start + 1:]:
        if line.strip().startswith('--'):
            try:
                options += shlex.split(line.strip())
            except ValueError:
                options.append(line.strip())
    return options


def buildconf_problems(lock: dict, system: str, options: list) -> list:
    problems = []
    if not options:
        return ['-buildconf printed no configuration']
    for option in options:
        if option.split('=', 1)[0] in lock['forbidden_options']:
            problems.append(f'-buildconf: {option}')
        for word in lock['forbidden_words']:
            if word in option.lower():
                problems.append(f'-buildconf: {option} names {word}')
    for option in configure_options(lock, system):
        if option not in options:
            problems.append(f'-buildconf lacks {option} of the lock')
    return problems


def program_run(command: list) -> str:
    result = subprocess.run(command, capture_output=True, text=True, timeout=120, encoding='utf-8', errors='replace')
    return result.stdout + result.stderr


def listing_problems(lock: dict, system: str, command: list, report: dict) -> list:
    problems = []
    for kind, option in LISTINGS.items():
        text = program_run([*command, '-hide_banner', option])
        if kind == 'protocol':
            found = parse_protocols(text)
            report[kind] = found
            want = expected(lock, 'protocol', system)
            if found['input'] != want or found['output'] != want:
                problems.append(f'-protocols: input {found["input"]}, output {found["output"]}; the lock says {want}')
            continue
        found = PARSERS[kind](text)
        report[kind] = found
        want = printed(lock, kind, system)
        if found != want:
            extra = sorted(set(found) - set(want))
            missing = sorted(set(want) - set(found))
            problems.append(f'{option}: {len(found)} names; more than the lock: {extra}; missing: {missing}')
    return problems


def run_problems(lock: dict, system: str, folder: pathlib.Path, label: str, prefix: list) -> tuple:
    suffix = '.exe' if system == 'windows-x64' else ''
    ffmpeg = [*prefix, str(folder / 'bin' / f'ffmpeg{suffix}')]
    ffprobe = [*prefix, str(folder / 'bin' / f'ffprobe{suffix}')]
    report, problems = {}, []
    version = program_run([*ffmpeg, '-hide_banner', '-version'])
    report['version'] = version.splitlines()[0] if version else ''
    if not version.startswith(f'ffmpeg version {lock["ffmpeg"]["version"]} '):
        problems.append(f'ffmpeg -version{label}: {report["version"]!r}')
    probe = program_run([*ffprobe, '-hide_banner', '-version'])
    if not probe.startswith(f'ffprobe version {lock["ffmpeg"]["version"]} '):
        problems.append(f'ffprobe -version{label}: {probe.splitlines()[0] if probe else ""!r}')
    options = buildconf_options(program_run([*ffmpeg, '-hide_banner', '-buildconf']))
    report['buildconf'] = options
    problems += [problem + label for problem in buildconf_problems(lock, system, options)]
    licence = ' '.join(program_run([*ffmpeg, '-hide_banner', '-L']).split())
    report['licence'] = licence[:200]
    if LGPL_LINE not in licence or 'General Public License as published' in licence.replace('Lesser General', ''):
        problems.append(f'ffmpeg -L{label} does not name the GNU LGPL 2.1 or later alone')
    problems += [problem + label for problem in listing_problems(lock, system, ffmpeg, report)]
    return problems, report


def read_archive(path: pathlib.Path) -> dict:
    with zipfile.ZipFile(path) as bundle:
        return {info.filename: bundle.read(info) for info in bundle.infolist() if not info.is_dir()}


def archive_modes(path: pathlib.Path) -> dict:
    with zipfile.ZipFile(path) as bundle:
        return {info.filename: (info.external_attr >> 16) & 0o777 for info in bundle.infolist() if not info.is_dir()}


def unpack_archive(files: dict, modes: dict, folder: pathlib.Path):
    for name, data in files.items():
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        if modes.get(name, 0o644) & 0o100:
            target.chmod(0o755)


def archive_problems(lock: dict, system: str, path: pathlib.Path, files: dict) -> list:
    problems = []
    if path.name != archive_name(lock, system):
        problems.append(f'{path.name}: not {archive_name(lock, system)}')
    if files.get('SHA256SUMS.txt', b'') != sums_text(files):
        problems.append('SHA256SUMS.txt does not give the sums of the files of the archive')
    info = files.get('BUILD-INFO.txt', b'').decode('utf-8', 'replace')
    if lock['ffmpeg']['commit'] not in info or 'configure (' not in info:
        problems.append('BUILD-INFO.txt does not name the commit of FFmpeg and its configure lines')
    for flag in CONFIG_FLAGS:
        if not re.search(rf'^config\.h \(\w+\): .*{flag} 0', info, re.MULTILINE):
            problems.append(f'BUILD-INFO.txt does not say {flag} 0')
    want = licence_files(lock, system)
    for name, data in sorted(want.items()):
        if text_bytes(files.get(name, b'')) != data:
            problems.append(f'{name} is missing from the archive or differs from the repository')
    runtime = {f'licenses/{entry["text"]}' for entry in lock.get('runtime_licences', {}).get(system, [])}
    for name in sorted(runtime):
        if not files.get(name):
            problems.append(f'no {name} in the archive')
    for name in sorted(files):
        if name.startswith('licenses/') and name not in want and name not in runtime and name != SOURCE_NOTE:
            problems.append(f'{name}: a licence file the lock does not name')
    if SOURCE_NOTE not in files:
        problems.append(f'no {SOURCE_NOTE}')
    allowed = set(want) | runtime | {SOURCE_NOTE, 'BUILD-INFO.txt', 'SHA256SUMS.txt'} | set(binaries(system, files))
    for name in sorted(set(files) - allowed):
        problems.append(f'{name}: a file the archive should not hold')
    problems += static_problems(lock, system, files)
    return problems


def command_check(args) -> int:
    lock = load_lock(args.lock)
    files = read_archive(args.archive)
    problems = archive_problems(lock, args.system, args.archive, files)
    report = {'archive': args.archive.name, 'sha256': sha256_file(args.archive), 'files': len(files)}
    if not problems:
        print(f'{args.archive.name}: {len(files)} files; sums, licences, imports and size as they should be')
    if args.run:
        modes = archive_modes(args.archive)
        with tempfile.TemporaryDirectory(prefix='ffmpeg-check-') as temporary:
            folder = pathlib.Path(temporary)
            unpack_archive(files, modes, folder)
            runs = [('', [])]
            if args.arch_x86_64:
                runs.append((' (x86_64 under Rosetta)', ['arch', '-x86_64']))
            for label, prefix in runs:
                found, data = run_problems(lock, args.system, folder, label, prefix)
                problems += found
                report[f'run{label}'] = data
    if args.report:
        args.report.write_text(json.dumps(report, indent=1) + '\n', encoding='utf-8')
    for problem in problems:
        print(f'::error::{problem}')
    if not problems and args.run:
        print('the programs: LGPL 2.1 or later, no GPL, non free or version 3 option, and the lists of the lock')
    return 1 if problems else 0


# --- the signed programs of Windows ------------------------------------------------------------------------------

def pe_without_signature(data: bytes) -> bytes:
    """A PE file without what an Authenticode signature changes: the checksum of its optional header and its
    certificate directory set to 0, and the file cut where its certificate table starts"""
    if len(data) < 0x40 or data[:2] != b'MZ':
        raise Failure('not a PE file')
    pe, = struct.unpack_from('<I', data, 0x3C)
    if data[pe:pe + 4] != b'PE\0\0':
        raise Failure('no PE signature')
    optional = pe + 24
    magic, = struct.unpack_from('<H', data, optional)
    if magic not in (0x20B, 0x10B):
        raise Failure(f'unknown optional header {magic:#x}')
    directories = optional + (112 if magic == 0x20B else 96)
    count, = struct.unpack_from('<I', data, directories - 4)
    out = bytearray(data)
    struct.pack_into('<I', out, optional + 64, 0)
    if count > 4:
        table, size = struct.unpack_from('<II', data, directories + 4 * 8)
        struct.pack_into('<II', out, directories + 4 * 8, 0, 0)
        if table and size:
            if table + size > len(data):
                raise Failure('the certificate table goes beyond the end of the file')
            out = out[:table]
    return bytes(out)


def has_certificate(data: bytes) -> bool:
    try:
        pe, = struct.unpack_from('<I', data, 0x3C)
        optional = pe + 24
        magic, = struct.unpack_from('<H', data, optional)
        directories = optional + (112 if magic == 0x20B else 96)
        count, = struct.unpack_from('<I', data, directories - 4)
        if count <= 4:
            return False
        table, size = struct.unpack_from('<II', data, directories + 4 * 8)
        return bool(table and size) and table + size <= len(data)
    except struct.error:
        return False


def only_signature_added(unsigned: bytes, signed: bytes) -> bool:
    bare, bare_signed = pe_without_signature(unsigned), pe_without_signature(signed)
    return bare_signed[:len(bare)] == bare and not bare_signed[len(bare):].strip(b'\0') \
        and len(bare_signed) - len(bare) < 8


def pe_names(files: dict) -> list:
    return sorted(name for name in files if name.startswith('bin/') and name.endswith(('.exe', '.dll')))


def command_program(args) -> int:
    if args.system != 'windows-x64':
        raise Failure('only the Windows programs are signed')
    files = read_archive(args.archive)
    for name in pe_names(files):
        target = args.out / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(files[name])
        print(f'{target}: {len(files[name])} bytes, SHA-256 {sha256(files[name])}')
    return 0


def command_signed(args) -> int:
    lock = load_lock(args.lock)
    if args.system != 'windows-x64':
        raise Failure('only the Windows programs are signed')
    files = read_archive(args.archive)
    info = files.get('BUILD-INFO.txt', b'').decode('utf-8')
    if SIGNED_LINE in info:
        raise Failure(f'{args.archive.name} is signed already')
    for name in pe_names(files):
        signed = (args.signed / name).read_bytes()
        if signed == files[name] or not has_certificate(signed):
            raise Failure(f'{name} is not signed')
        if not only_signature_added(files[name], signed):
            raise Failure(f'{name} is not the file of {args.archive.name} with a signature added')
        files[name] = signed
    files['BUILD-INFO.txt'] = (info.rstrip('\n') + '\n' + SIGNED_LINE + '\n').encode('utf-8')
    files['SHA256SUMS.txt'] = sums_text(files)
    problems = static_problems(lock, args.system, files)
    for problem in problems:
        print(f'::error::{problem}')
    if problems:
        return 1
    target = args.out / args.archive.name
    write_archive(target, files, args.system)
    print(f'{target.name}: {target.stat().st_size} bytes, SHA-256 {sha256_file(target)}, '
          f'{len(pe_names(files))} files signed')
    return 0


# --- the corresponding source ------------------------------------------------------------------------------------

def tar_add(bundle: tarfile.TarFile, name: str, data: bytes, mtime: int, mode: int = 0o644):
    info = tarfile.TarInfo(name)
    info.size, info.mtime, info.mode = len(data), mtime, mode
    info.uid = info.gid = 0
    info.uname = info.gname = ''
    bundle.addfile(info, io.BytesIO(data))


def command_source_archive(args) -> int:
    lock = load_lock(args.lock)
    mtime = int(os.environ.get('SOURCE_DATE_EPOCH') or 0)
    prefix = f'{args.tag}-sources'
    entries = {}
    for entry in source_entries(lock):
        path = args.cache / file_name(entry)
        if sha256_file(path) != entry['sha256']:
            raise Failure(f'{path.name} in {args.cache}: not the SHA-256 of the lock')
        entries[f'{prefix}/archives/{file_name(entry)}'] = path.read_bytes()
    recipe = [HERE / name for name in ('sources.lock', 'build.py', 'smoke.py', 'pe_imports.py', 'windows_sign.py',
                                       'requirements.txt')]
    recipe += sorted(LICENCES.iterdir()) + [WORKFLOW]
    for path in recipe:
        entries[f'{prefix}/recipe/{path.relative_to(ROOT).as_posix()}'] = path.read_bytes()
    for info in sorted(args.builds.glob('*/BUILD-INFO.txt')):
        entries[f'{prefix}/configure/{info.parent.name}-BUILD-INFO.txt'] = info.read_bytes()
    commit = args.commit or os.environ.get('GITHUB_SHA') or 'unknown'
    entries[f'{prefix}/README.txt'] = '\n'.join([
        f'The corresponding source of the release {args.tag} of {REPOSITORY} (GNU LGPL 2.1, section 6).',
        '',
        f'archives/   every source archive of ffmpeg/sources.lock, as downloaded and checked by its SHA-256',
        f'recipe/     ffmpeg/ and .github/workflows/ffmpeg.yml of {REPOSITORY} at {commit}',
        'configure/  the BUILD-INFO.txt of each archive: the toolchains and the exact configure lines',
        '',
        'Rebuild: python3 recipe/ffmpeg/build.py sources --dir SRC --cache archives, then build, archive and check as',
        'the jobs of recipe/.github/workflows/ffmpeg.yml do (in the container named by its digest for Windows and Linux).',
        '',
    ]).encode()
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode='w', format=tarfile.PAX_FORMAT) as bundle:
        for name in sorted(entries):
            mode = 0o755 if name.endswith(('.py',)) else 0o644
            tar_add(bundle, name, entries[name], mtime, mode)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_bytes(lzma.compress(raw.getvalue(), preset=6))
    print(f'{args.out.name}: {args.out.stat().st_size} bytes, {len(entries)} files, SHA-256 {sha256_file(args.out)}')
    return 0


# --- release -----------------------------------------------------------------------------------------------------

COMPONENTS = {'windows-x64': 'ffmpeg-lgpl-windows-x64', 'linux-x64': 'ffmpeg-lgpl-linux-x64',
              'macos-universal': 'ffmpeg-lgpl-macos-universal'}


def built_from(files: dict) -> str | None:
    found = re.search(rb'^Built by https://github\.com/\S+ at ([0-9a-f]{40})$', files.get('BUILD-INFO.txt', b''),
                      re.MULTILINE)
    return found.group(1).decode() if found else None


def signature_of(system: str, files: dict) -> str:
    if system == 'windows-x64':
        names = pe_names(files)
        signed = SIGNED_LINE.encode() in files.get('BUILD-INFO.txt', b'') and names and \
            all(has_certificate(files[name]) for name in names)
        return 'Authenticode, APROGSYS (Azure Artifact Signing)' if signed else 'none'
    return 'ad hoc' if system == 'macos-universal' else 'none'


def manifest(lock: dict, tag: str, repo: str, run_id: str, commit: str, date: str, archives: dict,
             sources: pathlib.Path) -> dict:
    base = f'https://github.com/{repo}/releases/download/{tag}/'
    entries = {}
    for system, path in archives.items():
        data = path.read_bytes()
        files = read_archive(path)
        modes = archive_modes(path)
        entries[COMPONENTS[system]] = {
            'system': system,
            'assetName': path.name,
            'url': base + path.name,
            'size': len(data),
            'sha256': sha256(data),
            'signature': signature_of(system, files),
            'archiveFiles': [{'path': name, 'size': len(content), 'sha256': sha256(content),
                              'mode': f'{modes.get(name, 0o644):04o}',
                              'executable': bool(modes.get(name, 0o644) & 0o100)}
                             for name, content in sorted(files.items())],
        }
    return {'name': 'ffmpeg-lgpl', 'tag': tag, 'repository': f'https://github.com/{repo}', 'commit': commit,
            'run': run_id, 'date': date, 'lock': lock['id'], 'licence': 'LGPL-2.1-or-later',
            'ffmpeg': {key: lock['ffmpeg'][key] for key in ('version', 'tag', 'commit', 'url', 'sha256')},
            'sources': {'assetName': sources.name, 'url': base + sources.name, 'size': sources.stat().st_size,
                        'sha256': sha256_file(sources)},
            'archives': entries}


def command_release(args) -> int:
    lock = load_lock(args.lock)
    if not re.fullmatch(r'ffmpeg-lgpl-\d{8}-\d+', args.tag):
        print(f'--tag {args.tag!r} is not ffmpeg-lgpl-<date>-<run>')
        return 2
    args.out.mkdir(parents=True, exist_ok=True)
    archives, problems, commits = {}, [], set()
    for system in SYSTEMS:
        source = args.archives / archive_name(lock, system)
        if not source.is_file():
            raise Failure(f'no {source.name} in {args.archives}')
        target = args.out / source.name
        if source.resolve() != target.resolve():
            shutil.copyfile(source, target)
        archives[system] = target
        files = read_archive(target)
        problems += [f'{target.name}: {problem}' for problem in archive_problems(lock, system, target, files)]
        commits.add(built_from(files))
        if system == 'windows-x64' and args.require_signed_windows and signature_of(system, files) == 'none':
            problems.append(f'{target.name}: its .exe and .dll files are not all signed, or BUILD-INFO.txt does not '
                            'say they are')
        if args.tag.encode() not in files.get(SOURCE_NOTE, b''):
            problems.append(f'{target.name}: {SOURCE_NOTE} does not name the release {args.tag}')
    if len(commits) != 1 or None in commits:
        problems.append(f'the three archives come from {sorted(str(c) for c in commits)}, not one commit')
    elif args.commit and next(iter(commits)) != args.commit:
        problems.append(f'the archives were built from {next(iter(commits))}, the release is at {args.commit}')
    sources = args.out / args.sources.name
    if args.sources.resolve() != sources.resolve():
        shutil.copyfile(args.sources, sources)
    for problem in problems:
        print(f'::error::{problem}')
    if problems:
        return 1
    record = manifest(lock, args.tag, args.repo, args.run, args.commit, args.date, archives, sources)
    json_name = f'ffmpeg-lgpl-{args.tag}.json'
    (args.out / json_name).write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8', newline='\n')
    made = sorted(path for path in args.out.iterdir() if path.is_file() and path.name != 'SHA256SUMS.txt')
    (args.out / 'SHA256SUMS.txt').write_text(''.join(f'{sha256_file(path)}  {path.name}\n' for path in made),
                                             encoding='utf-8', newline='\n')
    for path in [*made, args.out / 'SHA256SUMS.txt']:
        print(f'{path.stat().st_size:>10}  {sha256_file(path)}  {path.name}')
    if args.notes:
        rows = '\n'.join(f'| `{path.name}` | {path.stat().st_size} | `{sha256_file(path)}` |'
                         for path in archives.values())
        lines = []
        for system in SYSTEMS:
            info = read_archive(archives[system])['BUILD-INFO.txt'].decode('utf-8')
            lines += [line for line in info.splitlines() if line.startswith('configure (')]
        args.notes.write_text('\n'.join([
            f'ffmpeg and ffprobe {lock["ffmpeg"]["version"]} for Immuch360 Desktop (its 2D to 3D video conversion, '
            'experimental), built from pinned sources by `.github/workflows/ffmpeg.yml`. Not a release of the '
            'repository\'s libmpv builds, and never its latest release.',
            '',
            '- Licence: GNU LGPL version 2.1 or later as a whole (`--disable-gpl --disable-nonfree`, no '
            '`--enable-version3`); the licence texts in `licenses/` of each archive, the notices in `NOTICES.md`.',
            '- Encoders: H.264 and HEVC through the system (Media Foundation on Windows, VideoToolbox on macOS, VA-API '
            'on Linux), AV1 by SVT-AV1, AAC; no libx264, libx265, OpenH264, NVENC, AMF or QSV.',
            f'- Corresponding source (LGPL 2.1, section 6): `{sources.name}`.',
            f'- Manifest for a catalogue of components: `{json_name}`. Every file of the release: `SHA256SUMS.txt`.',
            f'- Built by https://github.com/{args.repo}/actions/runs/{args.run} from {args.commit}.',
            '',
            '| Archive | Bytes | SHA-256 |', '|---|---:|---|', rows, '',
            'Configure lines:', '', '```', *lines, '```', '',
        ]), encoding='utf-8', newline='\n')
    return 0


def command_verify(args) -> int:
    """The assets of a release as GitHub serves them, against its SHA256SUMS.txt and its manifest"""
    problems = []
    sums = {}
    for line in (args.dir / 'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
        digest, name = line.split('  ', 1)
        sums[name] = digest
    for name, digest in sorted(sums.items()):
        path = args.dir / name
        if not path.is_file():
            problems.append(f'{name}: in SHA256SUMS.txt, not in the release')
        elif sha256_file(path) != digest:
            problems.append(f'{name}: SHA-256 {sha256_file(path)}, SHA256SUMS.txt says {digest}')
    for path in sorted(args.dir.iterdir()):
        if path.is_file() and path.name != 'SHA256SUMS.txt' and path.name not in sums:
            problems.append(f'{path.name}: in the release, not in SHA256SUMS.txt')
    record = json.loads((args.dir / f'ffmpeg-lgpl-{args.tag}.json').read_text(encoding='utf-8'))
    entries = [*record['archives'].values(), record['sources']]
    for entry in entries:
        path = args.dir / entry['assetName']
        if not path.is_file():
            problems.append(f'{entry["assetName"]}: in the manifest, not in the release')
            continue
        if path.stat().st_size != entry['size'] or sha256_file(path) != entry['sha256']:
            problems.append(f'{entry["assetName"]}: not the size and SHA-256 of the manifest')
        if not entry['url'].endswith(f'/releases/download/{args.tag}/{entry["assetName"]}'):
            problems.append(f'{entry["assetName"]}: the manifest gives the address {entry["url"]}')
        if 'archiveFiles' in entry:
            files = read_archive(path)
            modes = archive_modes(path)
            listed = {item['path']: item for item in entry['archiveFiles']}
            if sorted(listed) != sorted(files):
                problems.append(f'{entry["assetName"]}: its files are not those of the manifest')
            for name, item in listed.items():
                data = files.get(name, b'')
                if len(data) != item['size'] or sha256(data) != item['sha256'] or \
                        f'{modes.get(name, 0):04o}' != item['mode']:
                    problems.append(f'{entry["assetName"]}: {name} is not as the manifest says')
    for problem in problems:
        print(f'::error::{problem}')
    if not problems:
        print(f'{len(sums)} assets as SHA256SUMS.txt says, {len(record["archives"])} archives and the sources as '
              f'ffmpeg-lgpl-{args.tag}.json says, every file of each archive included')
    return 1 if problems else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('--lock', type=pathlib.Path, default=LOCK)
    commands = parser.add_subparsers(dest='command', required=True)
    lock = commands.add_parser('lock')
    lock.add_argument('--system', choices=SYSTEMS, required=True)
    lock.add_argument('--github-output', action='store_true')
    sources = commands.add_parser('sources')
    sources.add_argument('--dir', type=pathlib.Path, required=True)
    sources.add_argument('--cache', type=pathlib.Path)
    sources.add_argument('--system', choices=SYSTEMS)
    build = commands.add_parser('build')
    build.add_argument('--system', choices=SYSTEMS, required=True)
    build.add_argument('--src', type=pathlib.Path, required=True)
    build.add_argument('--work', type=pathlib.Path, required=True)
    build.add_argument('--jobs', type=int, default=0)
    licences = commands.add_parser('licences')
    licences.add_argument('--src', type=pathlib.Path)
    archive = commands.add_parser('archive')
    archive.add_argument('--system', choices=SYSTEMS, required=True)
    archive.add_argument('--work', type=pathlib.Path, required=True)
    archive.add_argument('--src', type=pathlib.Path, required=True)
    archive.add_argument('--out', type=pathlib.Path, required=True)
    archive.add_argument('--tag', required=True)
    archive.add_argument('--commit')
    archive.add_argument('--repo', default=os.environ.get('GITHUB_REPOSITORY') or REPOSITORY)
    check = commands.add_parser('check')
    check.add_argument('--system', choices=SYSTEMS, required=True)
    check.add_argument('--archive', type=pathlib.Path, required=True)
    check.add_argument('--run', action='store_true')
    check.add_argument('--arch-x86-64', action='store_true')
    check.add_argument('--report', type=pathlib.Path)
    program = commands.add_parser('program')
    program.add_argument('--system', choices=SYSTEMS, required=True)
    program.add_argument('--archive', type=pathlib.Path, required=True)
    program.add_argument('--out', type=pathlib.Path, required=True)
    signed = commands.add_parser('signed')
    signed.add_argument('--system', choices=SYSTEMS, required=True)
    signed.add_argument('--archive', type=pathlib.Path, required=True)
    signed.add_argument('--signed', type=pathlib.Path, required=True)
    signed.add_argument('--out', type=pathlib.Path, required=True)
    source = commands.add_parser('source-archive')
    source.add_argument('--cache', type=pathlib.Path, required=True)
    source.add_argument('--builds', type=pathlib.Path, required=True)
    source.add_argument('--out', type=pathlib.Path, required=True)
    source.add_argument('--tag', required=True)
    source.add_argument('--commit')
    release = commands.add_parser('release')
    release.add_argument('--archives', type=pathlib.Path, required=True)
    release.add_argument('--sources', type=pathlib.Path, required=True)
    release.add_argument('--out', type=pathlib.Path, required=True)
    release.add_argument('--tag', required=True)
    release.add_argument('--commit', required=True)
    release.add_argument('--run', required=True)
    release.add_argument('--repo', default=os.environ.get('GITHUB_REPOSITORY') or REPOSITORY)
    release.add_argument('--date', default=time.strftime('%Y-%m-%d', time.gmtime()))
    release.add_argument('--notes', type=pathlib.Path)
    release.add_argument('--require-signed-windows', action='store_true')
    verify = commands.add_parser('verify')
    verify.add_argument('--dir', type=pathlib.Path, required=True)
    verify.add_argument('--tag', required=True)
    args = parser.parse_args(argv)
    try:
        return {'verify': command_verify, 'lock': command_lock, 'sources': command_sources, 'build': command_build,
                'licences': command_licences, 'archive': command_archive, 'check': command_check,
                'program': command_program, 'signed': command_signed, 'source-archive': command_source_archive,
                'release': command_release}[args.command](args)
    except (Failure, subprocess.CalledProcessError) as error:
        print(f'::error::{error}')
        return 1
    except (OSError, json.JSONDecodeError, KeyError) as error:
        print(f'::error::{type(error).__name__}: {error}')
        return 2


if __name__ == '__main__':
    sys.exit(main())
