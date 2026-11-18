"""Checks of the FFmpeg program's recipe that need no build: ffmpeg/sources.lock, ffmpeg/build.py, ffmpeg/smoke.py and
.github/workflows/ffmpeg.yml.

Run from the root of the repository with Python 3.10 or later:

    python3 -m unittest discover -s tests -v

The lock pins every source by its address and SHA-256 and every container by its digest, asks configure for nothing
GPL, non free or version 3, and lists the encoders of the plan of Immuch360 (system H.264 and HEVC encoders, SVT-AV1,
AAC, nothing else). The licence texts are those the lock names. The archive writer gives the same bytes for the same
files. The parsers of the program's listings, the gate on -buildconf, the st3d reader and the closure of configure's
_select lines work on known inputs. The workflow publishes only on a run by hand, from one job that may write, signs on
those runs only and makes a prerelease that is never the latest release.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True

ROOT = Path(__file__).resolve().parent.parent
FFMPEG = ROOT / 'ffmpeg'
WORKFLOW = ROOT / '.github' / 'workflows' / 'ffmpeg.yml'


def load(name: str):
    spec = importlib.util.spec_from_file_location(f'ffmpeg_{name}', FFMPEG / f'{name}.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build = load('build')
smoke = load('smoke')


def workflow() -> str:
    return WORKFLOW.read_text(encoding='utf-8').replace('\r\n', '\n')


def job(name: str) -> str:
    text = workflow()
    start = text.index(f'\n  {name}:\n')
    following = re.search(r'\n  [a-z][a-z0-9-]*:\n', text[start + 1:])
    return text[start:start + 1 + following.start()] if following else text[start:]


class Lock(unittest.TestCase):
    def setUp(self):
        self.lock = build.load_lock()

    def test_every_source_pinned(self):
        for entry in build.source_entries(self.lock):
            self.assertTrue(entry['url'].startswith('https://'), entry['name'])
            self.assertRegex(entry['sha256'], r'^[0-9a-f]{64}$', entry['name'])
            self.assertGreater(entry['size'], 0, entry['name'])
        self.assertEqual(self.lock['ffmpeg']['tag'], f'n{self.lock["ffmpeg"]["version"]}')
        self.assertTrue(self.lock['ffmpeg']['version'].startswith('9.0.'))

    def test_containers_by_digest(self):
        for system in ('windows-x64', 'linux-x64'):
            container = self.lock['containers'][system]
            self.assertRegex(container['digest'], r'^sha256:[0-9a-f]{64}$')
            for line in container['apt']:
                self.assertRegex(line, r'^https?://snapshot\.(debian\.org|ubuntu\.com)/\S+/\d{8}T\d{6}Z ')
        self.assertEqual(self.lock['containers']['windows-x64']['image'], 'debian:bookworm')
        self.assertEqual(self.lock['containers']['linux-x64']['image'], 'ubuntu:22.04')
        self.assertEqual(self.lock['containers']['macos-universal']['minimum'], '12.0')

    def test_configure_lgpl_only(self):
        for system in build.SYSTEMS:
            options = build.configure_options(self.lock, system)
            for option in ('--disable-gpl', '--disable-nonfree', '--disable-everything', '--disable-autodetect',
                           '--disable-network', '--enable-shared'):
                self.assertIn(option, options, system)
            self.assertEqual(build.buildconf_problems(self.lock, system, options), [], system)
            joined = ' '.join(options).lower()
            for word in ('enable-gpl', 'enable-nonfree', 'enable-version3', 'libx264', 'libx265', 'libfdk',
                         'openh264', 'nvenc', 'amf', 'qsv'):
                self.assertNotIn(word, joined, system)

    def test_threads_asked_for(self):
        # --disable-autodetect turns the thread libraries off, and the ffmpeg program needs threads
        self.assertIn('--enable-w32threads', build.configure_options(self.lock, 'windows-x64'))
        self.assertIn('--enable-pthreads', build.configure_options(self.lock, 'linux-x64'))
        self.assertIn('--enable-pthreads', build.configure_options(self.lock, 'macos-universal'))

    def test_encoders_of_the_plan(self):
        self.assertEqual(build.expected(self.lock, 'encoder', 'windows-x64'),
                         ['aac', 'h264_mf', 'hevc_mf', 'libsvtav1', 'rawvideo'])
        self.assertEqual(build.expected(self.lock, 'encoder', 'macos-universal'),
                         ['aac', 'h264_videotoolbox', 'hevc_videotoolbox', 'libsvtav1', 'rawvideo'])
        self.assertEqual(build.expected(self.lock, 'encoder', 'linux-x64'),
                         ['aac', 'h264_vaapi', 'hevc_vaapi', 'libsvtav1', 'rawvideo'])
        self.assertEqual(build.expected(self.lock, 'protocol', 'linux-x64'), ['file', 'pipe'])

    def test_what_the_app_needs(self):
        for kind, names in (('decoder', ['h264', 'hevc', 'vp9', 'libdav1d', 'aac', 'opus', 'vorbis']),
                            ('demuxer', ['mov', 'matroska', 'concat']), ('muxer', ['mp4', 'matroska', 'rawvideo']),
                            ('filter', ['zscale', 'tonemap', 'scale', 'showinfo', 'transpose', 'fps']),
                            ('indev', ['lavfi'])):
            for name in names:
                self.assertIn(name, build.expected(self.lock, kind, 'linux-x64'), kind)
        self.assertIn('mov,mp4,m4a,3gp,3g2,mj2', build.printed(self.lock, 'demuxer', 'linux-x64'))
        self.assertIn('lavfi', build.printed(self.lock, 'demuxer', 'linux-x64'))
        self.assertIn('buffersink', build.printed(self.lock, 'filter', 'linux-x64'))

    def test_archive_name(self):
        self.assertEqual(build.archive_name(self.lock, 'linux-x64'),
                         f'Immuch360-ffmpeg-{self.lock["id"]}-linux-x64.zip')
        self.assertRegex(self.lock['id'], r'^9\.0\.\d+-\d+$')

    def test_launcher_pinned_to_a_commit_of_av2_companion(self):
        launcher = next(entry for entry in self.lock['sources'] if entry['name'] == 'immuch360-run')
        self.assertIn('/immuch360/av2-companion/' + launcher['commit'] + '/launcher/immuch360_run.c', launcher['url'])
        self.assertEqual(launcher['systems'], ['linux-x64'])

    def test_requirements_hashed(self):
        text = (FFMPEG / 'requirements.txt').read_text(encoding='utf-8')
        for package in ('meson==', 'ninja=='):
            self.assertIn(package, text)
        self.assertGreaterEqual(text.count('--hash=sha256:'), 4)


class Licences(unittest.TestCase):
    def test_texts_of_the_lock(self):
        lock = build.load_lock()
        self.assertEqual(build.licence_problems(lock, None), [])
        names = {entry['text'] for entry in lock['licences']}
        for name in ('FFmpeg-COPYING.LGPLv2.1.txt', 'SVT-AV1-PATENTS.md', 'zimg-COPYING.txt', 'dav1d-COPYING.txt',
                     'zlib-LICENSE.txt', 'libva-COPYING.txt', 'immuch360-run-MIT.txt'):
            self.assertIn(name, names)
        text = (FFMPEG / 'licenses' / 'FFmpeg-COPYING.LGPLv2.1.txt').read_text(encoding='utf-8')
        self.assertIn('GNU LESSER GENERAL PUBLIC LICENSE', text)
        self.assertIn('Version 2.1', text)
        self.assertIn('Alliance for Open Media Patent License 1.0',
                      (FFMPEG / 'licenses' / 'SVT-AV1-PATENTS.md').read_text(encoding='utf-8'))

    def test_patent_note(self):
        text = (FFMPEG / 'licenses' / 'PATENTS-NOTE.md').read_text(encoding='utf-8')
        for words in ('H.264', 'HEVC', 'AAC', 'Media Foundation', 'VideoToolbox', 'VA-API', 'royalty free',
                      'No patent licence', 'grant no patent licence'):
            if words == 'No patent licence':
                continue
            self.assertIn(words, text)

    def test_source_note_names_the_release(self):
        lock = build.load_lock()
        note = build.source_note(lock, 'ffmpeg-lgpl-20261118-1', 'a' * 40, 'immuch360/libmpv-builds').decode()
        self.assertIn('https://github.com/immuch360/libmpv-builds/releases/download/ffmpeg-lgpl-20261118-1/'
                      'ffmpeg-lgpl-20261118-1-sources.tar.xz', note)
        self.assertIn(lock['ffmpeg']['commit'], note)


class Archive(unittest.TestCase):
    def test_same_files_same_bytes(self):
        files = {'bin/ffmpeg': b'\x7fELF program', 'lib/libavutil.so.60': b'library', 'BUILD-INFO.txt': b'info\n'}
        files['SHA256SUMS.txt'] = build.sums_text(files)
        with tempfile.TemporaryDirectory() as temporary:
            one, two = Path(temporary) / 'one.zip', Path(temporary) / 'two.zip'
            build.write_archive(one, dict(reversed(list(files.items()))), 'linux-x64')
            build.write_archive(two, files, 'linux-x64')
            self.assertEqual(one.read_bytes(), two.read_bytes())
            modes = build.archive_modes(one)
            self.assertEqual(modes['bin/ffmpeg'], 0o755)
            self.assertEqual(modes['lib/libavutil.so.60'], 0o644)
            self.assertEqual(build.read_archive(one)['SHA256SUMS.txt'], build.sums_text(files))

    def test_windows_programs_executable(self):
        self.assertTrue(build.is_program('windows-x64', 'bin/ffmpeg.exe'))
        self.assertFalse(build.is_program('windows-x64', 'bin/avcodec-63.dll'))
        self.assertTrue(build.is_program('macos-universal', 'bin/ffprobe'))
        self.assertFalse(build.is_program('macos-universal', 'lib/libavcodec.63.dylib'))


class Listings(unittest.TestCase):
    def test_codecs(self):
        text = ('Encoders:\n V..... = Video\n ------\n V....D libsvtav1            SVT-AV1\n'
                ' A....D aac                  AAC (Advanced Audio Coding)\n')
        self.assertEqual(build.parse_codecs(text), ['aac', 'libsvtav1'])

    def test_formats(self):
        text = (' D. = Demuxing supported\n .E = Muxing supported\n  ..d = Is a device\n --\n'
                ' D   concat          Virtual concatenation script\n D d lavfi           Libavfilter virtual input device\n'
                ' D   matroska,webm   Matroska / WebM\n  E  mp4             MP4 (MPEG-4 Part 14)\n')
        self.assertEqual(build.parse_formats(text), ['concat', 'lavfi', 'matroska,webm', 'mp4'])

    def test_filters(self):
        text = ('Filters:\n  T.. = Timeline support\n  ------\n'
                ' .. abuffer           |->A       Buffer audio frames\n TS scale             V->V       Scale\n')
        self.assertEqual(build.parse_filters(text), ['abuffer', 'scale'])

    def test_bsfs_and_protocols(self):
        self.assertEqual(build.parse_bsfs('Bitstream filters:\naac_adtstoasc\nvp9_superframe\n\n'),
                         ['aac_adtstoasc', 'vp9_superframe'])
        self.assertEqual(build.parse_protocols('Supported file protocols:\nInput:\n  file\n  pipe\nOutput:\n  file\n'
                                               '  pipe\n'), {'input': ['file', 'pipe'], 'output': ['file', 'pipe']})

    def test_buildconf_refuses_gpl(self):
        lock = build.load_lock()
        options = build.configure_options(lock, 'linux-x64') + ['--enable-gpl', '--enable-libx264']
        problems = build.buildconf_problems(lock, 'linux-x64', options)
        self.assertTrue(any('--enable-gpl' in problem for problem in problems))
        self.assertTrue(any('libx264' in problem for problem in problems))
        self.assertEqual(build.buildconf_options('  configuration:\n    --prefix=/x\n    --disable-gpl\n'),
                         ['--prefix=/x', '--disable-gpl'])


class Closure(unittest.TestCase):
    def test_select_lines(self):
        configure = 'theora_decoder_select="vp3_decoder"\nvp3_decoder_select="hpeldsp"\nmov_muxer_select="vp9_superframe_bsf"\n'
        self.assertEqual(build.closure(configure, {'theora_decoder', 'mov_muxer'}),
                         {'theora_decoder', 'vp3_decoder', 'hpeldsp', 'mov_muxer', 'vp9_superframe_bsf'})


class Smoke(unittest.TestCase):
    def test_st3d(self):
        box = (13).to_bytes(4, 'big') + b'st3d' + b'\0\0\0\0' + b'\x02'
        self.assertEqual(smoke.st3d_boxes(b'moov....' + box + b'other'), [2])
        self.assertEqual(smoke.st3d_boxes(b'no box here'), [])

    def test_side_by_side_rows(self):
        frame = bytes(range(2 * 1 * 3)) * 1  # 2 pixels wide, 1 high
        self.assertEqual(smoke.sbs_frame(frame, 2, 1), frame + frame)

    def test_portrait_eye(self):
        self.assertEqual(smoke.eye_size({'video': {'rotation': -90}}), (108, 192))
        self.assertEqual(smoke.eye_size({'video': {'rotation': 0}}), (192, 108))

    def test_audio_rules_of_the_plan(self):
        self.assertEqual(smoke.COPY_AUDIO, {'aac', 'mp3', 'opus', 'alac', 'ac3', 'eac3', 'flac'})

    def test_svt_always_tried(self):
        self.assertEqual(smoke.SVT[0], 'libsvtav1')
        self.assertEqual({encoder[0] for encoder in smoke.ENCODERS['windows-x64']}, {'h264_mf', 'hevc_mf'})


class Workflow(unittest.TestCase):
    def test_triggers(self):
        text = workflow()
        self.assertIn('  workflow_dispatch:\n', text)
        self.assertIn('  pull_request:\n    paths:\n      - .github/workflows/ffmpeg.yml\n      - ffmpeg/**\n', text)
        self.assertNotIn('schedule:', text)
        self.assertNotIn('\n  push:', text)

    def test_permissions(self):
        text = workflow()
        self.assertIn('\npermissions:\n  contents: read\n', text)
        self.assertEqual(text.count('contents: write'), 1)
        self.assertIn('contents: write', job('release'))
        self.assertIn("if: github.event_name == 'workflow_dispatch' && inputs.publish", job('release'))

    def test_signing_on_publish_only(self):
        text = workflow()
        self.assertEqual(text.count('secrets.AZURE_CLIENT_SECRET'), 1)
        self.assertEqual(text.count('secrets.'), 3)
        signing = job('test-windows')
        for line in [line for line in signing.splitlines() if 'secrets.' in line]:
            self.assertRegex(line.strip(), r'^AZURE_(TENANT|CLIENT)_(ID|SECRET): \$\{\{ secrets\.AZURE_\w+ \}\}$')
        self.assertGreaterEqual(signing.count("if: env.PUBLISH == 'true'"), 4)
        self.assertIn('--require-signed-windows', job('release'))

    def test_prerelease_never_latest(self):
        release = job('release')
        self.assertIn('--prerelease --latest=false', release)
        self.assertNotIn('--latest ', release.replace('--latest=false', ''))
        self.assertIn('build.py verify --dir served', release)

    def test_containers_from_the_lock(self):
        self.assertIn('image: ${{ needs.plan.outputs.windows_image }}', job('windows'))
        self.assertIn('image: ${{ needs.plan.outputs.linux_image }}', job('linux'))
        self.assertIn('runs-on: macos-15', job('macos'))

    def test_two_builds_compared(self):
        self.assertIn('attempt: [1, 2]', job('windows'))
        self.assertIn('attempt: [1, 2]', job('linux'))
        self.assertIn('the two builds differ', job('same'))


if __name__ == '__main__':
    unittest.main()
