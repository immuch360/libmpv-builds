"""Checks of the recipe that need no build: the pins, the overlay, the release rules and the y4m check.

Run from the root of the repository with Python 3.10 or later, bash and git:

    python3 -m unittest discover -s tests -v

Windows: windows/sources.lock and windows/pin_sources.sh, so that a run builds the commits of the lock, never the head
a branch has on the day of the run. macOS: macos/packages.lock.nix at the FFmpeg and mpv commits of the Windows build,
every archive pinned by its SHA-256, the overlay copying every file the recipe reads and refusing a recipe it was not
made for, and FFmpeg's options (the y4m demuxer and the rawvideo decoder, nothing GPL or nonfree). The workflow: the
inputs and their fallbacks agree, and only a run by hand that asks for it publishes. The y4m check: its fixtures are
y4m as the AV2 decoder of Immuch360 writes them, and it fails the reports it must fail.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = ROOT / '.github' / 'workflows' / 'build.yml'
WINDOWS = ROOT / 'windows'
MACOS = ROOT / 'macos'
LOCK = WINDOWS / 'sources.lock'
PIN_SOURCES = WINDOWS / 'pin_sources.sh'
MACOS_LOCK = MACOS / 'packages.lock.nix'
OVERLAY = MACOS / 'apply_overlay.sh'
FFMPEG_MESON = MACOS / 'mk-pkg-ffmpeg-meson.build'
CHECK_Y4M = MACOS / 'check_y4m.py'

HAVE_BASH_AND_GIT = shutil.which('bash') is not None and shutil.which('git') is not None


def workflow() -> str:
    return WORKFLOW.read_text(encoding='utf-8').replace('\r\n', '\n')


def lock_lines() -> list[str]:
    return [line.strip() for line in LOCK.read_text(encoding='utf-8').splitlines()
            if line.strip() and not line.startswith('#')]


def windows_commits() -> dict[str, str]:
    return {line.split()[0]: line.split()[1] for line in lock_lines()}


def macos_entries() -> dict[str, dict[str, str]]:
    entry = re.compile(r'^  ([\w-]+) = \{\s*version = "([^"]*)";\s*url = "([^"]*)";\s*sha256 = "([^"]*)";', re.M)
    return {m[1]: {'version': m[2], 'url': m[3], 'sha256': m[4]}
            for m in entry.finditer(MACOS_LOCK.read_text(encoding='utf-8'))}


def env_default(name: str) -> str:
    """The fallback of the workflow variable [name] for runs without inputs"""
    match = re.search(rf"^  {name}: \$\{{\{{ inputs\.[a-z_]+ \|\| '([^']+)' \}}\}}", workflow(), re.M)
    if match is None:
        raise AssertionError(f'no fallback for {name} in {WORKFLOW}')
    return match[1]


def input_default(name: str) -> str:
    """The default of the workflow_dispatch input [name]"""
    match = re.search(rf"^      {name}:\n(?:        .*\n)*?        default: '?([^'\n]+)'?\n", workflow(), re.M)
    if match is None:
        raise AssertionError(f'no default for the input {name}')
    return match[1]


def job_condition(job: str) -> str:
    """The "if:" of [job], folded lines joined"""
    lines = workflow().split('\n')
    start = lines.index(f'  {job}:')
    parts: list[str] = []
    for i in range(start + 1, len(lines)):
        if re.match(r'^  \S', lines[i]):
            break
        if lines[i].startswith('    if:'):
            parts.append(lines[i][len('    if:'):].replace('>-', '').strip())
            for following in lines[i + 1:]:
                if not following.startswith('      ') or following.strip().endswith(':'):
                    break
                parts.append(following.strip())
            break
    return ' '.join(parts).strip()


def meson_text() -> str:
    return FFMPEG_MESON.read_text(encoding='utf-8').replace('\r\n', '\n')


def meson_list(meson: str, name: str) -> list[str]:
    found = re.search(rf'^{name} = \[\n(.*?)^\]', meson, re.M | re.S)
    if found is None:
        raise AssertionError(f'no list {name} in {FFMPEG_MESON}')
    return [m[1] for m in (re.match(r"^\s+'([^']+)',", line) for line in found[1].split('\n')) if m]


def recipe_meson(copy: str) -> str:
    """The recipe's own meson.build as the copy holds it: the copy without its lines that say Immuch360"""
    return '\n'.join(line for line in copy.split('\n') if 'Immuch360' not in line)


class SourcesLock(unittest.TestCase):
    def test_one_commit_per_package_each_named_once(self):
        for line in lock_lines():
            self.assertRegex(line, r'^[a-z0-9_.+-]+ [0-9a-f]{40}$')
        names = [line.split()[0] for line in lock_lines()]
        self.assertEqual(len(set(names)), len(names))

    def test_pins_the_toolchain_and_the_libraries_not_ffmpeg_and_mpv(self):
        names = set(windows_commits())
        self.assertTrue({'llvm', 'mingw-w64', 'cppwinrt', 'libxml2', 'dav1d', 'libass', 'freetype2'} <= names)
        self.assertNotIn('ffmpeg', names, 'FFmpeg is pinned by the ffmpeg_ref input')
        self.assertNotIn('mpv', names, 'mpv is pinned by the mpv_ref input')


@unittest.skipUnless(HAVE_BASH_AND_GIT and os.name != 'nt', 'pin_sources.sh runs on Linux, with bash and git')
class PinSources(unittest.TestCase):
    def git(self, cwd: Path, *args: str) -> str:
        run = subprocess.run(['git', '-c', 'user.name=test', '-c', 'user.email=test@example.invalid',
                              '-c', 'init.defaultBranch=main', '-c', 'commit.gpgsign=false', *args],
                             cwd=cwd, capture_output=True, text=True)
        if run.returncode != 0:
            raise AssertionError(f'git {" ".join(args)}: {run.stderr}')
        return run.stdout.strip()

    def setUp(self):
        self.root = Path(tempfile.mkdtemp(prefix='libmpv_pins_'))
        origin = self.root / 'origin'
        origin.mkdir()
        self.git(origin, 'init', '-q')
        self.commits = []
        for n in (1, 2, 3):
            (origin / 'file.txt').write_text(str(n))
            self.git(origin, 'add', 'file.txt')
            self.git(origin, 'commit', '-q', '-m', f'commit {n}')
            self.commits.append(self.git(origin, 'rev-parse', 'HEAD'))
        # A clone per package, as the recipe's download step leaves them, and an archive package without git data
        for name in ('dav1d', 'libass', 'ffmpeg'):
            self.git(self.root, 'clone', '-q', str(origin), str(self.root / 'src' / name))
        (self.root / 'src' / 'libiconv').mkdir(parents=True)
        (self.root / 'src' / 'libiconv' / 'configure').write_text('')

    def tearDown(self):
        shutil.rmtree(self.root)

    def write_lock(self, pins: dict[str, str]):
        body = ''.join(f'{name} {commit}\n' for name, commit in pins.items())
        (self.root / 'sources.lock').write_text('# package commit\n' + body)

    def pin(self, mode: str, *packages: str) -> subprocess.CompletedProcess:
        return subprocess.run(['bash', str(PIN_SOURCES), str(self.root / 'sources.lock'), str(self.root / 'src'), mode,
                               *packages], capture_output=True, text=True)

    def head(self, name: str) -> str:
        return self.git(self.root / 'src' / name, 'rev-parse', 'HEAD')

    def test_checks_every_package_out_at_its_pin_and_prints_the_lock_lines(self):
        self.write_lock({'dav1d': self.commits[0], 'libass': self.commits[2]})
        run = self.pin('pinned', 'dav1d', 'libass', 'ffmpeg', 'libiconv')
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(self.head('dav1d'), self.commits[0])
        self.assertEqual((self.root / 'src' / 'dav1d' / 'file.txt').read_text(), '1')
        self.assertEqual(run.stdout.strip().split('\n'), [f'dav1d {self.commits[0]}', f'libass {self.commits[2]}'])
        self.assertIn(f'dav1d: {self.commits[2]} -> {self.commits[0]}', run.stderr)
        # FFmpeg stays where the workflow input put it; the archive is not a git package
        self.assertEqual(self.head('ffmpeg'), self.commits[2])

    def test_stops_on_a_git_package_without_a_pin_and_prints_the_line_to_add(self):
        self.write_lock({'dav1d': self.commits[1]})
        run = self.pin('pinned', 'dav1d', 'libass')
        self.assertEqual(run.returncode, 1)
        self.assertIn('Not pinned', run.stderr)
        self.assertIn(f'libass {self.commits[2]}', run.stderr)

    def test_stops_on_a_pin_that_is_not_a_commit_of_the_repository(self):
        self.write_lock({'dav1d': 'f' * 40})
        self.assertNotEqual(self.pin('pinned', 'dav1d').returncode, 0)
        self.assertEqual(self.head('dav1d'), self.commits[2])

    def test_heads_moves_nothing_and_prints_the_lines_of_the_heads(self):
        self.write_lock({'dav1d': self.commits[0]})
        run = self.pin('heads', 'dav1d', 'libass', 'mpv')
        self.assertEqual(run.returncode, 0, run.stderr)
        self.assertEqual(run.stdout.strip().split('\n'), [f'dav1d {self.commits[2]}', f'libass {self.commits[2]}'])
        self.assertEqual(self.head('dav1d'), self.commits[2])

    def test_refuses_an_unknown_mode_and_a_missing_lock(self):
        self.write_lock({})
        self.assertEqual(self.pin('latest', 'dav1d').returncode, 2)
        (self.root / 'sources.lock').unlink()
        self.assertEqual(self.pin('pinned', 'dav1d').returncode, 2)


class Workflow(unittest.TestCase):
    def test_runs_without_inputs_build_what_a_dispatch_with_the_defaults_builds(self):
        for env, name in (('RECIPE_REPOSITORY', 'recipe_repository'), ('RECIPE_REF', 'recipe_ref'),
                          ('FFMPEG_REF', 'ffmpeg_ref'), ('MPV_REF', 'mpv_ref'),
                          ('MACOS_RECIPE_REF', 'macos_recipe_ref'), ('MACOS_TARGET', 'macos_target')):
            self.assertEqual(env_default(env), input_default(name), env)

    def test_publishes_only_for_a_run_by_hand_that_asks_for_it(self):
        for job in ('publish', 'macos-publish'):
            condition = job_condition(job)
            self.assertIn("github.event_name == 'workflow_dispatch' && inputs.publish", condition, job)
        self.assertIn("needs.sources.outputs.pinned == 'true'", job_condition('publish'))

    def test_no_schedule_and_no_push_trigger(self):
        on = workflow().split('\non:\n', 1)[1].split('\npermissions:', 1)[0]
        triggers = re.findall(r'^  ([a-z_]+):', on, re.M)
        self.assertEqual(triggers, ['workflow_dispatch', 'pull_request'])

    def test_the_repository_paths_the_jobs_read_exist(self):
        for path in set(re.findall(r'builds/((?:windows|macos)/[\w.-]+)', workflow())):
            self.assertTrue((ROOT / path).is_file(), path)


class MacosPins(unittest.TestCase):
    def test_every_archive_is_pinned_by_the_sha256_of_what_is_downloaded(self):
        entries = macos_entries()
        self.assertTrue(entries)
        for name, entry in entries.items():
            if name == 'fftools-ffi':
                continue  # a Nix hash, for the encoders flavor only, which is not built
            self.assertRegex(entry['sha256'], r'^[0-9a-f]{64}$', name)
            self.assertTrue(entry['url'].startswith('https://'), name)

    def test_ffmpeg_and_mpv_at_the_commits_the_windows_build_defaults_to(self):
        entries = macos_entries()
        self.assertIn(env_default('FFMPEG_REF'), entries['ffmpeg']['url'])
        self.assertIn(env_default('MPV_REF'), entries['mpv']['url'])

    def test_libplacebo_fast_float_and_the_vulkan_headers_at_the_commits_of_sources_lock(self):
        entries, windows = macos_entries(), windows_commits()
        self.assertIn(windows['libplacebo'], entries['libplacebo']['url'])
        self.assertIn(windows['fast_float'], entries['fast_float']['url'])
        self.assertIn(windows['vulkan-header'], entries['vulkan-headers']['url'])
        for name in ('ffmpeg', 'mpv', 'libplacebo', 'fast_float', 'vulkan-headers'):
            commit = re.search(r'/archive/([0-9a-f]{40})\.tar\.gz$', entries[name]['url'])
            self.assertIsNotNone(commit, f'{name}: an archive of a full commit')
            self.assertTrue(commit[1].startswith(entries[name]['version']), f'{name}: its version starts its commit')

    def test_the_overlay_copies_every_nix_file_patch_and_meson_build_of_the_folder(self):
        script = OVERLAY.read_text(encoding='utf-8')
        files = [f.name for f in MACOS.iterdir() if f.suffix in ('.nix', '.patch', '.build')]
        self.assertIn('mk-pkg-ffmpeg-meson.build', files)
        for name in files:
            self.assertIn(f'$here/{name}', script, f'{name} is not copied over the recipe')


class MacosFfmpeg(unittest.TestCase):
    def test_the_default_video_flavor_reads_a_y4m_over_http(self):
        meson = meson_text()
        video = meson_list(meson, 'video_default_options')
        self.assertIn('--enable-demuxer=yuv4mpegpipe', video)
        self.assertIn('--enable-decoder=rawvideo', video)
        audio = meson_list(meson, 'audio_default_options')
        self.assertIn('--enable-protocol=http', audio)
        self.assertIn('--enable-protocol=tcp', audio)
        self.assertIn("if flavor == 'default'\n    options += audio_default_options\n    if variant == 'video'\n"
                      '        options += video_default_options\n', meson)

    def test_nothing_gpl_or_nonfree_in_the_default_flavor(self):
        meson = meson_text()
        for name in ('common_options', 'audio_common_options', 'video_common_options', 'audio_default_options',
                     'video_default_options'):
            for option in meson_list(meson, name):
                self.assertNotIn('--enable-gpl', option, name)
                self.assertNotIn('--enable-nonfree', option, name)

    def test_the_copy_is_the_recipes_meson_build_and_the_lines_that_say_immuch360(self):
        copy = meson_text()
        pin = re.search(r'^ffmpeg_meson_sha256=([0-9a-f]{64})$', OVERLAY.read_text(encoding='utf-8'), re.M)
        self.assertIsNotNone(pin, 'apply_overlay.sh checks the SHA-256 of the meson.build it replaces')
        self.assertEqual(hashlib.sha256(recipe_meson(copy).encode()).hexdigest(), pin[1])
        added = [m[1] for m in (re.match(r"^\s+'([^']+)',", line) for line in copy.split('\n') if 'Immuch360' in line)
                 if m]
        self.assertEqual(sorted(added), ['--enable-decoder=rawvideo', '--enable-demuxer=yuv4mpegpipe'])


@unittest.skipUnless(shutil.which('bash') and os.name != 'nt', 'apply_overlay.sh runs on Linux and macOS')
class OverlayOverARecipe(unittest.TestCase):
    def setUp(self):
        self.copy = meson_text()
        self.recipe = Path(tempfile.mkdtemp(prefix='libmpv_overlay_'))
        min_version = "min_version   = '-mmacosx-version-min=10.9'\n"
        files = {name: "# the recipe's\n" for name in (
            'packages.lock.nix', 'nix/packages/mk-pkg-ffmpeg/default.nix', 'nix/packages/mk-pkg-mpv/default.nix',
            'nix/packages/mk-out-libs/default.nix', 'nix/packages/mk-pkg-libpng/default.nix', 'patches/README')}
        files['nix/packages/mk-pkg-ffmpeg/meson.build'] = recipe_meson(self.copy)
        files['cross-files/macos-arm64.ini'] = min_version
        files['cross-files/macos-amd64.ini'] = min_version
        for name, content in files.items():
            (self.recipe / name).parent.mkdir(parents=True, exist_ok=True)
            (self.recipe / name).write_text(content)

    def tearDown(self):
        shutil.rmtree(self.recipe)

    def overlay(self) -> subprocess.CompletedProcess:
        return subprocess.run(['bash', str(OVERLAY), str(self.recipe)], capture_output=True, text=True)

    def test_puts_the_ffmpeg_options_over_the_meson_build_it_was_made_from(self):
        run = self.overlay()
        self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
        self.assertEqual((self.recipe / 'nix/packages/mk-pkg-ffmpeg/meson.build').read_text(), self.copy)
        self.assertEqual((self.recipe / 'packages.lock.nix').read_text(), MACOS_LOCK.read_text())
        self.assertIn('-mmacosx-version-min=12.0', (self.recipe / 'cross-files/macos-arm64.ini').read_text())

    def test_refuses_a_recipe_whose_ffmpeg_meson_build_is_not_the_one_the_copy_was_made_from(self):
        meson = self.recipe / 'nix/packages/mk-pkg-ffmpeg/meson.build'
        changed = meson.read_text() + '# a newer recipe\n'
        meson.write_text(changed)
        run = self.overlay()
        self.assertNotEqual(run.returncode, 0)
        self.assertIn('mk-pkg-ffmpeg/meson.build', run.stdout + run.stderr)
        self.assertEqual(meson.read_text(), changed)


# The fixture as check_y4m.py makes it: 320x180, 32 frames at 16 per second, frame k one grey of luma 16 + 6k
WIDTH, HEIGHT, FRAMES, FPS = 320, 180, 32, 16


def y4m_header(depth: int) -> str:
    colour = 'C420' if depth == 8 else 'C420p10'
    return f'YUV4MPEG2 W{WIDTH} H{HEIGHT} F{FPS}:1 Ip A1:1 {colour} XCOLORRANGE=LIMITED\n'


def frame_offset(depth: int, frame: int) -> int:
    return len(y4m_header(depth)) + frame * (6 + WIDTH * HEIGHT * 3 // 2 * (1 if depth == 8 else 2))


def grey(frame: int) -> float:
    return 6 * frame * 255 / 219


def shown(value: float) -> dict:
    return {'w': WIDTH, 'h': HEIGHT, 'bgr': [value, value, value]}


def good_report(depth: int) -> dict:
    """The report of y4m_probe.c for a libmpv that reads the fixture of [depth] bits"""
    return {
        'source': f'/tmp/fixture-{depth}bit.y4m', 'mpv-version': 'mpv v0.41.0', 'file-format': 'yuv4mpegpipe',
        'current-tracks/video/codec': 'rawvideo', 'video-params/pixelformat': 'yuv420p' if depth == 8 else 'yuv420p10',
        'video-params/w': str(WIDTH), 'video-params/h': str(HEIGHT), 'container-fps': 16.0, 'duration': 2.0,
        'estimated-frame-count': str(FRAMES), 'firstTime': 0.0, 'firstFrame': shown(grey(0)),
        'forwardTime': 1.5, 'forwardFrame': shown(grey(24) + 0.4), 'backTime': 0.5, 'backFrame': shown(grey(8) - 0.3),
        'endTime': 1.9375, 'frame-drop-count': '0', 'decoder-frame-drop-count': '0', 'error': None, 'log': '',
    }


class Y4mCheck(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix='libmpv_y4m_'))

    def tearDown(self):
        shutil.rmtree(self.folder)

    def script(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(CHECK_Y4M), *args], capture_output=True, text=True)

    def evaluate(self, report: dict, depth: int, ranges: list[int] | None = None) -> subprocess.CompletedProcess:
        path = self.folder / 'report.json'
        path.write_text(json.dumps(report))
        extra = ['--http', '--ranges', *map(str, ranges)] if ranges is not None else []
        return self.script('evaluate', str(path), '--depth', str(depth), *extra)

    def test_the_fixtures_are_y4m_as_the_av2_decoder_writes_them(self):
        for depth in (8, 10):
            out = self.folder / f'fixture-{depth}.y4m'
            run = self.script('fixture', str(out), '--depth', str(depth))
            self.assertEqual(run.returncode, 0, run.stdout + run.stderr)
            data = out.read_bytes()
            self.assertEqual(len(data), frame_offset(depth, FRAMES))
            self.assertEqual(data[:len(y4m_header(depth))].decode('ascii'), y4m_header(depth))
            luma_samples = WIDTH * HEIGHT
            for frame in (0, 8, 24, FRAMES - 1):
                start = frame_offset(depth, frame)
                self.assertEqual(data[start:start + 6], b'FRAME\n', f'{depth} bit, frame {frame}')
                body = data[start + 6:]
                if depth == 8:
                    self.assertEqual(body[0], 16 + 6 * frame)
                    self.assertEqual(body[luma_samples - 1], 16 + 6 * frame)
                    self.assertEqual(body[luma_samples], 128, 'chroma at the middle')
                else:
                    sample = lambda i: int.from_bytes(body[2 * i:2 * i + 2], 'little')  # noqa: E731
                    self.assertEqual(sample(0), (16 + 6 * frame) * 4)
                    self.assertEqual(sample(luma_samples - 1), (16 + 6 * frame) * 4)
                    self.assertEqual(sample(luma_samples), 512, 'chroma at the middle')

    def test_a_report_of_a_libmpv_that_reads_the_fixture_passes_from_a_file_and_over_http(self):
        for depth in (8, 10):
            run = self.evaluate(good_report(depth), depth)
            self.assertEqual(run.returncode, 0, run.stdout)
            self.assertNotIn('FAILED', run.stdout)
            # The seek back of FFmpeg's demuxer starts one frame before the target
            http = self.evaluate(good_report(depth), depth, ranges=[0, frame_offset(depth, 7)])
            self.assertEqual(http.returncode, 0, http.stdout)
            self.assertIn('passed: over HTTP, the seek back asked for a range from a frame', http.stdout)

    def test_a_libmpv_without_the_y4m_demuxer_fails(self):
        run = self.evaluate({'source': 'http://127.0.0.1:50000/fixture-8bit.y4m', 'error': 'unrecognized file format',
                             'log': '[error] ffmpeg/demuxer: Requested format yuv4mpegpipe not found'}, 8)
        self.assertEqual(run.returncode, 1)
        self.assertIn('FAILED: opened and played (unrecognized file format)', run.stdout)
        self.assertIn('FAILED: demuxer yuv4mpegpipe', run.stdout)
        self.assertIn('FAILED: decoder rawvideo', run.stdout)

    def test_10_bit_read_as_8_bit_fails(self):
        run = self.evaluate({**good_report(10), 'video-params/pixelformat': 'yuv420p', 'firstFrame': shown(37)}, 10)
        self.assertEqual(run.returncode, 1)
        self.assertIn('FAILED: pixel format yuv420p10', run.stdout)
        self.assertIn('FAILED: first frame: frame 0', run.stdout)

    def test_a_seek_to_the_wrong_frame_a_seek_read_through_or_a_dropped_frame_fails(self):
        wrong = self.evaluate({**good_report(8), 'forwardFrame': shown(grey(23))}, 8)
        self.assertEqual(wrong.returncode, 1)
        self.assertIn('FAILED: exact seek forward: frame 24', wrong.stdout)
        read_through = self.evaluate(good_report(8), 8, ranges=[0])
        self.assertEqual(read_through.returncode, 1)
        self.assertIn('FAILED: over HTTP, the seek back asked for a range from a frame', read_through.stdout)
        dropped = self.evaluate({**good_report(10), 'decoder-frame-drop-count': '2'}, 10)
        self.assertEqual(dropped.returncode, 1)
        self.assertIn('FAILED: played to the last frame, none dropped', dropped.stdout)


if __name__ == '__main__':
    unittest.main()
