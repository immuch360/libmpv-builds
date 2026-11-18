#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 FreeKC
"""What Immuch360 Desktop asks of its FFmpeg program, tried on the program of an archive.

The 2D to 3D video conversion of the app (store/m2/release-49/lots/video3d-plan.md of its notes, sections 2.1, 2.4 and
2.5) runs the program three ways: it decodes the source to raw RGB frames on a pipe (stdout) with their timestamps
(-stats_enc_pre), it encodes raw side by side frames from a pipe (stdin) into Matroska segments marked left right, and
it joins the segments with the sound and the tags of the source into an MP4 whose st3d box says left right. This script
does the same on small clips, with the encoders the runner allows (SVT-AV1 always), and checks every result.

  smoke.py fixtures --out DIR [--ffmpeg PROGRAM] [--ffprobe PROGRAM]
      the clips, made with the FFmpeg of the runner (any build: the clips are test inputs, never shipped) from FFmpeg's
      own test patterns: H.264, HEVC (8 bit, and 10 bit HLG turned 90 degrees as phones store it), AV1, VP9, VP8,
      MPEG-2, ProRes and MJPEG in MP4, Matroska, WebM, MPEG-TS, MOV and AVI, with AAC, Opus, Vorbis, AC-3, MP2 and PCM
      sound, a variable frame rate, two sound tracks and subtitles; DIR/fixtures.json says what each one holds
  smoke.py run --system SYSTEM --archive FILE --fixtures DIR [--work DIR] [--report FILE] [--arch-x86-64]
      the checks on the programs of the archive; the report (JSON) and a Markdown table for the run summary
      (--summary FILE)

Only the Python standard library is used. Exit codes: 0 good, 1 a check failed, 2 bad arguments or missing files.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile

sys.dont_write_bytecode = True

# The sound the final MP4 takes as it is (plan, section 2.5); any other is made AAC by FFmpeg's own encoder
COPY_AUDIO = {'aac', 'mp3', 'opus', 'alac', 'ac3', 'eac3', 'flac'}
# The tone map of the plan for HLG and PQ sources (section 2.1), checked on ai1 on 18 November 2026
TONE_MAP = ('zscale=t=linear:npl=203,format=gbrpf32le,zscale=p=bt709,tonemap=hable:desat=0,'
            'zscale=t=bt709:m=bt709:r=tv,format=rgb24')
EYE = (192, 108)
TAGS = ('creation_time', 'location', 'make', 'model')

# The clips: name, the arguments of the FFmpeg of the runner (after -y), and what the decode and SBS checks do with it
VIDEO = 'testsrc2=size=320x180:rate=30:duration=2'
SOUND = 'sine=frequency=440:sample_rate=48000:duration=2'
SOUND_FR = 'sine=frequency=660:sample_rate=48000:duration=2'
FIXTURES = [
    ('h264_aac.mp4', ['-f', 'lavfi', '-i', VIDEO, '-f', 'lavfi', '-i', SOUND, '-c:v', 'libx264', '-pix_fmt', 'yuv420p',
                      '-g', '30', '-c:a', 'aac', '-ac', '2', '-b:a', '128k',
                      '-metadata', 'creation_time=2024-05-01T10:00:00.000000Z',
                      '-metadata', 'location=+48.8584+002.2945/', '-metadata', 'make=Immuch360',
                      '-metadata', 'model=Fixture', '-movflags', '+use_metadata_tags'], {'sbs': True}),
    ('hevc_aac.mkv', ['-f', 'lavfi', '-i', VIDEO, '-f', 'lavfi', '-i', SOUND, '-c:v', 'libx265', '-pix_fmt', 'yuv420p',
                      '-x265-params', 'log-level=error', '-c:a', 'aac', '-ac', '2'], {}),
    ('hevc10_hlg.mp4', ['-f', 'lavfi', '-i', VIDEO, '-f', 'lavfi', '-i', SOUND, '-c:v', 'libx265',
                        '-pix_fmt', 'yuv420p10le', '-x265-params',
                        'log-level=error:colorprim=bt2020:transfer=arib-std-b67:colormatrix=bt2020nc',
                        '-color_primaries', 'bt2020', '-color_trc', 'arib-std-b67', '-colorspace', 'bt2020nc',
                        '-tag:v', 'hvc1', '-c:a', 'aac', '-ac', '2'], {'intermediate': True}),
    ('av1_opus.mp4', ['-f', 'lavfi', '-i', VIDEO, '-f', 'lavfi', '-i', SOUND, '-c:v', 'libaom-av1', '-cpu-used', '8',
                      '-row-mt', '1', '-crf', '40', '-b:v', '0', '-c:a', 'libopus', '-ac', '2'], {}),
    ('vp9_opus.webm', ['-f', 'lavfi', '-i', VIDEO, '-f', 'lavfi', '-i', SOUND, '-c:v', 'libvpx-vp9', '-deadline',
                       'realtime', '-cpu-used', '8', '-b:v', '400k', '-c:a', 'libopus', '-ac', '2'], {}),
    ('vp8_vorbis.webm', ['-f', 'lavfi', '-i', VIDEO, '-f', 'lavfi', '-i', SOUND, '-c:v', 'libvpx', '-deadline',
                         'realtime', '-b:v', '400k', '-c:a', 'libvorbis', '-ac', '2'], {'sbs': True}),
    ('h264_2audio_subs.mkv', ['-f', 'lavfi', '-i', VIDEO, '-f', 'lavfi', '-i', SOUND, '-f', 'lavfi', '-i', SOUND_FR,
                              '-i', '{subtitles}', '-map', '0:v', '-map', '1:a', '-map', '2:a', '-map', '3:s',
                              '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a:0', 'ac3', '-ac:a:0', '2',
                              '-c:a:1', 'aac', '-ac:a:1', '2', '-c:s', 'srt', '-metadata:s:a:0', 'language=eng',
                              '-metadata:s:a:1', 'language=fra'], {'sbs': True}),
    ('mpeg2_mp2.ts', ['-f', 'lavfi', '-i', VIDEO, '-f', 'lavfi', '-i', SOUND, '-c:v', 'mpeg2video', '-q:v', '4',
                      '-c:a', 'mp2', '-ac', '2'], {}),
    ('h264_vfr.mp4', ['-f', 'lavfi', '-i', VIDEO, '-f', 'lavfi', '-i', SOUND, '-vf', "select='not(eq(mod(n,7),6))'",
                      '-fps_mode', 'passthrough', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ac', '2'],
     {}),
    ('prores_pcm.mov', ['-f', 'lavfi', '-i', VIDEO, '-f', 'lavfi', '-i', SOUND, '-c:v', 'prores_ks', '-profile:v', '0',
                        '-c:a', 'pcm_s16le', '-ac', '2'], {'sbs': True}),
    ('mjpeg_pcm.avi', ['-f', 'lavfi', '-i', VIDEO, '-f', 'lavfi', '-i', SOUND, '-c:v', 'mjpeg', '-q:v', '5',
                       '-c:a', 'pcm_s16le', '-ac', '2'], {}),
]
# The phone style clip: the 10 bit HLG HEVC turned 90 degrees by its display matrix, as phones store a portrait video
ROTATED = ('hevc10_hlg_rot90.mp4', 'hevc10_hlg.mp4', {'sbs': True, 'tone_map': True})


class Failure(Exception):
    pass


def run_text(command: list, timeout: int = 300) -> subprocess.CompletedProcess:
    return subprocess.run([str(part) for part in command], capture_output=True, text=True, timeout=timeout,
                          encoding='utf-8', errors='replace')


# --- fixtures ----------------------------------------------------------------------------------------------------

def probe(ffprobe: str, path: pathlib.Path) -> dict:
    result = run_text([ffprobe, '-v', 'error', '-count_frames', '-show_format', '-show_streams', '-of', 'json', path])
    if result.returncode != 0:
        raise Failure(f'{path.name}: ffprobe failed: {result.stderr.strip()}')
    data = json.loads(result.stdout)
    video = next(stream for stream in data['streams'] if stream['codec_type'] == 'video')
    rotation = 0
    for side in video.get('side_data_list', []):
        if 'rotation' in side:
            rotation = int(side['rotation'])
    return {
        'video': {'codec': video['codec_name'], 'width': video['width'], 'height': video['height'],
                  'frames': int(video['nb_read_frames']), 'rate': video['r_frame_rate'],
                  'pix_fmt': video.get('pix_fmt'), 'transfer': video.get('color_transfer'), 'rotation': rotation},
        'audio': [{'codec': stream['codec_name'], 'channels': stream.get('channels', 2)}
                  for stream in data['streams'] if stream['codec_type'] == 'audio'],
        'subtitles': sum(1 for stream in data['streams'] if stream['codec_type'] == 'subtitle'),
        'format': data['format']['format_name'],
        'tags': {key: value for key, value in data['format'].get('tags', {}).items()
                 if key in TAGS or 'location' in key},
    }


def command_fixtures(args) -> int:
    args.out.mkdir(parents=True, exist_ok=True)
    subtitles = args.out / 'subtitles.srt'
    subtitles.write_text('1\n00:00:00,000 --> 00:00:01,500\nA subtitle the conversion leaves out\n', encoding='utf-8')
    records = {}
    for name, arguments, roles in FIXTURES:
        target = args.out / name
        command = [args.ffmpeg, '-hide_banner', '-v', 'error', '-y',
                   *[str(subtitles) if part == '{subtitles}' else part for part in arguments], target]
        result = run_text(command)
        if result.returncode != 0:
            raise Failure(f'{name}: {result.stderr.strip()}')
        if not roles.get('intermediate'):
            records[name] = {**probe(args.ffprobe, target), **{k: v for k, v in roles.items() if k == 'sbs'}}
    name, source, roles = ROTATED
    result = run_text([args.ffmpeg, '-hide_banner', '-v', 'error', '-y', '-display_rotation:v:0', '90',
                       '-i', args.out / source, '-map', '0', '-c', 'copy', args.out / name])
    if result.returncode != 0:
        raise Failure(f'{name}: {result.stderr.strip()}')
    (args.out / source).unlink()
    records[name] = {**probe(args.ffprobe, args.out / name), **roles}
    if abs(records[name]['video']['rotation']) != 90:
        raise Failure(f'{name}: the display matrix says {records[name]["video"]["rotation"]} degrees, not 90')
    subtitles.unlink()
    version = run_text([args.ffmpeg, '-version']).stdout.splitlines()[0]
    (args.out / 'fixtures.json').write_text(json.dumps({'made_by': version, 'clips': records}, indent=1) + '\n',
                                            encoding='utf-8')
    for name, record in records.items():
        video = record['video']
        print(f'{name}: {video["codec"]} {video["width"]}x{video["height"]} {video["frames"]} frames at '
              f'{video["rate"]}, rotation {video["rotation"]}, sound {[a["codec"] for a in record["audio"]]}, '
              f'{record["subtitles"]} subtitle tracks, tags {sorted(record["tags"])}')
    return 0


# --- the checks --------------------------------------------------------------------------------------------------

class Programs:
    def __init__(self, folder: pathlib.Path, system: str, prefix: list):
        suffix = '.exe' if system == 'windows-x64' else ''
        self.ffmpeg = [*prefix, str(folder / 'bin' / f'ffmpeg{suffix}')]
        self.ffprobe = [*prefix, str(folder / 'bin' / f'ffprobe{suffix}')]

    def probe(self, path: pathlib.Path) -> dict:
        result = run_text([*self.ffprobe, '-v', 'error', '-count_frames', '-show_format', '-show_streams', '-of',
                           'json', path])
        if result.returncode != 0:
            raise Failure(f'ffprobe {path.name}: {result.stderr.strip()[-500:]}')
        return json.loads(result.stdout)


def eye_size(record: dict) -> tuple:
    """The eye of the plan, scaled down for the test: portrait when the display matrix turns the frames a quarter"""
    width, height = EYE
    if abs(record['video']['rotation']) == 90:
        return height, width
    return width, height


def decode_command(programs: Programs, source: pathlib.Path, record: dict, size: tuple, stats: pathlib.Path) -> list:
    width, height = size
    filters = []
    if record.get('tone_map') or record['video'].get('transfer') in ('arib-std-b67', 'smpte2084'):
        filters.append(TONE_MAP)
    filters.append(f'scale={width}:{height}:flags=area,format=rgb24')
    return [*programs.ffmpeg, '-nostdin', '-hide_banner', '-v', 'error', '-threads', '2', '-i', source,
            '-map', '0:v:0', '-an', '-sn', '-dn', '-fps_mode', 'passthrough', '-vf', ','.join(filters),
            '-stats_enc_pre', stats, '-stats_enc_pre_fmt', '{n} {pts} {tb}', '-f', 'rawvideo', 'pipe:1']


def decode_frames(programs: Programs, source: pathlib.Path, record: dict, size: tuple, stats: pathlib.Path):
    """Each frame of the source as RGB24 bytes, read from the program's stdout as the app reads it"""
    command = decode_command(programs, source, record, size, stats)
    frame = size[0] * size[1] * 3
    process = subprocess.Popen([str(part) for part in command], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    errors = []
    reader = threading.Thread(target=lambda: errors.append(process.stderr.read()), daemon=True)
    reader.start()
    buffered = b''
    while True:
        block = process.stdout.read(1 << 20)
        if not block:
            break
        buffered += block
        while len(buffered) >= frame:
            yield buffered[:frame]
            buffered = buffered[frame:]
    code = process.wait()
    reader.join()
    if code != 0 or buffered:
        text = errors[0].decode('utf-8', 'replace') if errors else ''
        raise Failure(f'decode of {source.name}: exit {code}, {len(buffered)} bytes left over; {text.strip()[-400:]}')


def stats_problems(stats: pathlib.Path, frames: int, name: str) -> list:
    lines = [line.split() for line in stats.read_text(encoding='utf-8').splitlines() if line.strip()]
    problems = []
    if len(lines) != frames:
        problems.append(f'{name}: -stats_enc_pre wrote {len(lines)} lines for {frames} frames')
    try:
        stamps = [int(line[1]) for line in lines]
        if any(later <= earlier for earlier, later in zip(stamps, stamps[1:])):
            problems.append(f'{name}: the timestamps of -stats_enc_pre do not grow')
        if lines and not re.fullmatch(r'\d+/\d+', lines[0][2]):
            problems.append(f'{name}: no time base in -stats_enc_pre ({lines[0]})')
    except (IndexError, ValueError):
        problems.append(f'{name}: -stats_enc_pre lines not "n pts tb": {lines[:2]}')
    return problems


def shown_size(programs: Programs, source: pathlib.Path) -> tuple | None:
    """The size of the first frame after autorotation, as the showinfo filter logs it"""
    result = run_text([*programs.ffmpeg, '-nostdin', '-hide_banner', '-v', 'info', '-i', source, '-map', '0:v:0',
                       '-frames:v', '1', '-vf', 'showinfo', '-f', 'null', '-'])
    match = re.search(r'\bs:(\d+)x(\d+)\b', result.stderr)
    return (int(match.group(1)), int(match.group(2))) if match else None


ENCODERS = {
    'windows-x64': [('h264_mf', ['-c:v', 'h264_mf', '-hw_encoding', '1'], 'nv12'),
                    ('h264_mf', ['-c:v', 'h264_mf'], 'nv12'),
                    ('hevc_mf', ['-c:v', 'hevc_mf'], 'nv12')],
    'macos-universal': [('h264_videotoolbox', ['-c:v', 'h264_videotoolbox', '-b:v', '18M'], 'nv12'),
                        ('h264_videotoolbox', ['-c:v', 'h264_videotoolbox', '-allow_sw', '1', '-b:v', '18M'], 'nv12'),
                        ('hevc_videotoolbox', ['-c:v', 'hevc_videotoolbox', '-allow_sw', '1', '-b:v', '9M'], 'nv12')],
    'linux-x64': [('h264_vaapi', ['-c:v', 'h264_vaapi', '-low_power', '0', '-qp', '22'], 'vaapi'),
                  ('hevc_vaapi', ['-c:v', 'hevc_vaapi', '-low_power', '0', '-qp', '24'], 'vaapi')],
}
SVT = ('libsvtav1', ['-c:v', 'libsvtav1', '-preset', '10', '-crf', '30'], 'yuv420p')
RENDER_NODE = '/dev/dri/renderD128'


def encoder_input(kind: str) -> tuple:
    """The device options before the input and the filter after it for an encoder of the plan"""
    if kind == 'vaapi':
        return ['-vaapi_device', RENDER_NODE], 'format=nv12,hwupload'
    return [], f'format={kind}'


def one_second(programs: Programs, encoder: tuple, size: str = '3840x1080') -> dict:
    """The test of the plan before a job (section 2.4): 30 frames at the real size into the null muxer"""
    name, options, kind = encoder
    device, vf = encoder_input(kind)
    if kind == 'vaapi' and not os.path.exists(RENDER_NODE):
        return {'encoder': name, 'options': options, 'ok': False, 'why': f'no {RENDER_NODE} on this runner'}
    started = time.monotonic()
    result = run_text([*programs.ffmpeg, '-nostdin', '-hide_banner', '-v', 'error', *device, '-f', 'lavfi', '-i',
                       f'color=c=gray:s={size}:r=30', '-frames:v', '30', '-vf', vf, *options, '-f', 'null', '-'])
    seconds = round(time.monotonic() - started, 2)
    return {'encoder': name, 'options': options, 'ok': result.returncode == 0, 'seconds': seconds,
            'why': result.stderr.strip()[-300:] if result.returncode else ''}


def sbs_frame(frame: bytes, width: int, height: int) -> bytes:
    """Left eye and right eye side by side; the right eye is the left one here (no depth in this test)"""
    row = width * 3
    return b''.join(frame[r * row:(r + 1) * row] * 2 for r in range(height))


def encode_segments(programs: Programs, source: pathlib.Path, record: dict, encoder: tuple, folder: pathlib.Path,
                    rate: str) -> tuple:
    """The frames of the source decoded, made side by side and written by two encoder processes as two segments"""
    width, height = eye_size(record)
    name, options, kind = encoder
    device, vf = encoder_input(kind)
    if kind != 'vaapi':
        vf = f'scale=out_color_matrix=bt709:out_range=tv,{vf}'
    total = record['video']['frames']
    cut = total // 2
    segments, written, encoders = [], 0, []

    def start(index: int):
        target = folder / f'seg-{index:04d}.seg'
        command = [*programs.ffmpeg, '-nostdin', '-hide_banner', '-v', 'error', *device, '-f', 'rawvideo',
                   '-pix_fmt', 'rgb24', '-s', f'{2 * width}x{height}', '-framerate', rate, '-i', 'pipe:0', '-vf', vf,
                   *options, '-g', '60', '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
                   '-color_range', 'tv', '-metadata:s:v:0', 'stereo_mode=left_right', '-f', 'matroska', target]
        log = open(folder / f'seg-{index:04d}.log', 'wb')
        process = subprocess.Popen([str(part) for part in command], stdin=subprocess.PIPE, stderr=log)
        segments.append(target)
        encoders.append((process, log))
        return process

    stats = folder / 'pts.txt'
    current = start(1)
    for frame in decode_frames(programs, source, record, (width, height), stats):
        if written == cut:
            current.stdin.close()
            current = start(2)
        current.stdin.write(sbs_frame(frame, width, height))
        written += 1
    current.stdin.close()
    problems = []
    for index, (process, log) in enumerate(encoders, 1):
        code = process.wait(timeout=600)
        log.close()
        if code != 0:
            text = (folder / f'seg-{index:04d}.log').read_text(encoding='utf-8', errors='replace')
            problems.append(f'{source.name} with {name}: segment {index} exit {code}: {text.strip()[-300:]}')
    if written != total:
        problems.append(f'{source.name}: {written} frames decoded, {total} expected')
    problems += stats_problems(stats, written, source.name)
    return segments, problems


def st3d_boxes(data: bytes) -> list:
    """The stereo mode of each st3d box of an MP4 file (a box of 13 bytes: size, type, version and flags, mode)"""
    modes = []
    for match in re.finditer(b'st3d', data):
        at = match.start()
        if at >= 4 and int.from_bytes(data[at - 4:at], 'big') == 13 and at + 9 <= len(data):
            modes.append(data[at + 8])
    return modes


def final_mux(programs: Programs, segments: list, source: pathlib.Path, record: dict, target: pathlib.Path) -> list:
    listing = target.parent / 'segments.txt'
    listing.write_text(''.join(f"file '{segment.name}'\n" for segment in segments), encoding='utf-8')
    audio = []
    for index, stream in enumerate(record['audio']):
        if stream['codec'] in COPY_AUDIO:
            audio += [f'-c:a:{index}', 'copy']
        else:
            audio += [f'-c:a:{index}', 'aac', f'-b:a:{index}', '384k' if stream['channels'] > 2 else '192k']
    result = run_text([*programs.ffmpeg, '-nostdin', '-hide_banner', '-v', 'error', '-f', 'concat', '-safe', '0',
                       '-i', listing, '-i', source, '-map', '0:v', '-map', '1:a?', '-map_metadata', '1', '-c:v', 'copy',
                       *audio, '-strict', 'unofficial', '-movflags', '+faststart+use_metadata_tags', target])
    if result.returncode != 0:
        return [f'final mux of {source.name}: {result.stderr.strip()[-400:]}']
    return []


def output_problems(programs: Programs, target: pathlib.Path, record: dict, encoder: str) -> tuple:
    problems = []
    width, height = eye_size(record)
    modes = st3d_boxes(target.read_bytes())
    if modes != [2]:
        problems.append(f'{target.name}: st3d boxes {modes}, not one box with mode 2 (left right)')
    data = programs.probe(target)
    video = [stream for stream in data['streams'] if stream['codec_type'] == 'video']
    audio = [stream for stream in data['streams'] if stream['codec_type'] == 'audio']
    found = {'st3d': modes, 'streams': [stream['codec_name'] for stream in data['streams']]}
    if len(video) != 1:
        problems.append(f'{target.name}: {len(video)} video streams')
    else:
        stream = video[0]
        found.update(size=f'{stream["width"]}x{stream["height"]}', frames=int(stream.get('nb_read_frames', 0)))
        if (stream['width'], stream['height']) != (2 * width, height):
            problems.append(f'{target.name}: {stream["width"]}x{stream["height"]}, not {2 * width}x{height}')
        if int(stream.get('nb_read_frames', 0)) != record['video']['frames']:
            problems.append(f'{target.name}: {stream.get("nb_read_frames")} frames, the source has '
                            f'{record["video"]["frames"]}')
        # FFmpeg 9 writes, with -strict unofficial, the st3d box and Apple's vexu box (eyes) beside it; its own
        # reader then gives the type of vexu, which says nothing of the packing ("unspecified"). The app reads the st3d
        # box (spatial_media and spherical_probe), checked above; ffprobe must still see stereo side data
        sides = [side.get('side_data_type', '') + ':' + str(side.get('type', '')) for side in
                 stream.get('side_data_list', [])]
        found['ffprobe_stereo'] = sides
        found['vexu'] = b'vexu' in target.read_bytes()
        if not any(side.startswith('Stereo 3D') for side in sides):
            problems.append(f'{target.name}: ffprobe reads no Stereo 3D side data ({sides})')
    want = [stream['codec'] if stream['codec'] in COPY_AUDIO else 'aac' for stream in record['audio']]
    got = [stream['codec_name'] for stream in audio]
    if got != want:
        problems.append(f'{target.name}: sound {got}, the plan gives {want}')
    tags = data['format'].get('tags', {})
    found['tags'] = sorted(tags)
    for key in record['tags']:
        if key not in tags:
            problems.append(f'{target.name}: the tag {key} of the source is lost')
    return problems, found


def remux_problems(programs: Programs, segment: pathlib.Path, folder: pathlib.Path) -> list:
    """A Matroska file marked left right remuxed to MP4 as it is: one st3d box, mode 2 (the study's check)"""
    target = folder / 'remux.mp4'
    result = run_text([*programs.ffmpeg, '-nostdin', '-hide_banner', '-v', 'error', '-i', segment, '-c', 'copy',
                       '-strict', 'unofficial', '-movflags', '+faststart', target])
    if result.returncode != 0:
        return [f'remux of {segment.name}: {result.stderr.strip()[-300:]}']
    modes = st3d_boxes(target.read_bytes())
    return [] if modes == [2] else [f'remux of {segment.name}: st3d boxes {modes}, not [2]']


def checks(programs: Programs, system: str, fixtures: pathlib.Path, work: pathlib.Path, full: bool) -> tuple:
    clips = json.loads((fixtures / 'fixtures.json').read_text(encoding='utf-8'))['clips']
    report = {'decode': {}, 'encoders': [], 'sbs': {}}
    problems = []
    for name, record in clips.items():
        size = eye_size(record)
        stats = work / f'{name}.pts.txt'
        try:
            frames = sum(1 for _ in decode_frames(programs, fixtures / name, record, size, stats))
        except Failure as error:
            problems.append(str(error))
            report['decode'][name] = {'ok': False}
            continue
        found = stats_problems(stats, frames, name)
        if frames != record['video']['frames']:
            found.append(f'{name}: {frames} frames decoded, the source has {record["video"]["frames"]}')
        if abs(record['video']['rotation']) == 90:
            shown = shown_size(programs, fixtures / name)
            want = (record['video']['height'], record['video']['width'])
            if shown != want:
                found.append(f'{name}: showinfo gives {shown} after autorotation, not {want}')
        report['decode'][name] = {'ok': not found, 'frames': frames, 'codec': record['video']['codec'],
                                  'size': f'{size[0]}x{size[1]}'}
        problems += found
    encoders = [SVT, *ENCODERS[system]] if full else [SVT]
    passed = {}
    for encoder in encoders:
        result = one_second(programs, encoder)
        report['encoders'].append(result)
        if result['ok'] and encoder[0] not in passed:
            passed[encoder[0]] = encoder
    if 'libsvtav1' not in passed:
        problems.append(f'libsvtav1 fails the one second test: {report["encoders"][0]["why"]}')
    first_segment = None
    for name, record in clips.items():
        if not record.get('sbs'):
            continue
        for label, encoder in passed.items():
            if label != 'libsvtav1' and name != 'h264_aac.mp4':
                continue
            folder = work / f'sbs-{label}-{name}'
            folder.mkdir(parents=True, exist_ok=True)
            rate = record['video']['rate']
            segments, found = encode_segments(programs, fixtures / name, record, encoder, folder, rate)
            target = folder / f'{pathlib.Path(name).stem}_3D_LRF_Full_SBS.mp4'
            entry = {'encoder': label}
            if not found:
                found += final_mux(programs, segments, fixtures / name, record, target)
            if not found:
                more, data = output_problems(programs, target, record, label)
                found += more
                entry.update(data)
                first_segment = first_segment or segments[0]
            entry['ok'] = not found
            report['sbs'][f'{name} {label}'] = entry
            problems += found
    if first_segment:
        found = remux_problems(programs, first_segment, work)
        report['remux'] = {'ok': not found}
        problems += found
    else:
        problems.append('no segment was written: the remux check could not run')
    return problems, report


def summary_text(system: str, reports: dict) -> str:
    lines = [f'### FFmpeg program, {system}: what the app asks of it', '']
    for label, report in reports.items():
        lines += [f'**{label}**', '', '| Clip | Codec | Frames | Decoded to RGB on a pipe |', '|---|---|---:|---|']
        for name, entry in report['decode'].items():
            lines.append(f'| {name} | {entry.get("codec", "")} | {entry.get("frames", "")} | '
                         f'{"yes" if entry["ok"] else "**no**"} |')
        lines += ['', '| Encoder | Options | 30 frames of 3840x1080 | Seconds |', '|---|---|---|---:|']
        for entry in report['encoders']:
            why = '' if entry['ok'] else f' ({entry["why"][:120]})'
            lines.append(f'| {entry["encoder"]} | `{" ".join(entry["options"][2:])}` | '
                         f'{"passes" if entry["ok"] else "fails" + why} | {entry.get("seconds", "")} |')
        lines += ['', '| Side by side MP4 | Encoder | Size | Frames | st3d | vexu | Streams | OK |',
                  '|---|---|---|---:|---|---|---|---|']
        for name, entry in report['sbs'].items():
            lines.append(f'| {name.split()[0]} | {entry["encoder"]} | {entry.get("size", "")} | '
                         f'{entry.get("frames", "")} | {entry.get("st3d", "")} | {entry.get("vexu", "")} | '
                         f'{", ".join(entry.get("streams", []))} | '
                         f'{"yes" if entry["ok"] else "**no**"} |')
        if 'remux' in report:
            lines.append(f'\nMatroska marked left right remuxed to MP4: {"one st3d box, mode 2" if report["remux"]["ok"] else "**failed**"}')
        lines.append('')
    return '\n'.join(lines) + '\n'


def command_run(args) -> int:
    with zipfile.ZipFile(args.archive) as bundle:
        files = {info.filename: (bundle.read(info), (info.external_attr >> 16) & 0o777)
                 for info in bundle.infolist() if not info.is_dir()}
    work = args.work or pathlib.Path(tempfile.mkdtemp(prefix='ffmpeg-smoke-'))
    if work.exists():
        shutil.rmtree(work)
    folder = work / 'program'
    for name, (data, mode) in files.items():
        target = folder / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        if mode & 0o100:
            target.chmod(0o755)
    runs = [('native ' + platform.machine(), [], True)]
    if args.arch_x86_64:
        runs.append(('x86_64 under Rosetta', ['arch', '-x86_64'], False))
    problems, reports = [], {}
    for label, prefix, full in runs:
        place = work / re.sub(r'\W+', '-', label)
        place.mkdir(parents=True)
        found, report = checks(Programs(folder, args.system, prefix), args.system, args.fixtures, place, full)
        problems += [f'{problem} ({label})' for problem in found]
        reports[label] = report
    if args.report:
        args.report.write_text(json.dumps(reports, indent=1) + '\n', encoding='utf-8')
    text = summary_text(args.system, reports)
    print(text)
    if args.summary:
        with open(args.summary, 'a', encoding='utf-8') as stream:
            stream.write(text)
    for problem in problems:
        print(f'::error::{problem}')
    if not problems:
        print('every clip decoded to RGB on a pipe with its timestamps; side by side MP4 files with one st3d box, '
              'mode 2, the sound and the tags of the source')
    return 1 if problems else 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest='command', required=True)
    fixtures = commands.add_parser('fixtures')
    fixtures.add_argument('--out', type=pathlib.Path, required=True)
    fixtures.add_argument('--ffmpeg', default='ffmpeg')
    fixtures.add_argument('--ffprobe', default='ffprobe')
    smoke = commands.add_parser('run')
    smoke.add_argument('--system', choices=('windows-x64', 'linux-x64', 'macos-universal'), required=True)
    smoke.add_argument('--archive', type=pathlib.Path, required=True)
    smoke.add_argument('--fixtures', type=pathlib.Path, required=True)
    smoke.add_argument('--work', type=pathlib.Path)
    smoke.add_argument('--report', type=pathlib.Path)
    smoke.add_argument('--summary', type=pathlib.Path)
    smoke.add_argument('--arch-x86-64', action='store_true')
    args = parser.parse_args(argv)
    try:
        return {'fixtures': command_fixtures, 'run': command_run}[args.command](args)
    except Failure as error:
        print(f'::error::{error}')
        return 1
    except (OSError, json.JSONDecodeError, KeyError, subprocess.SubprocessError) as error:
        print(f'::error::{type(error).__name__}: {error}')
        return 2


if __name__ == '__main__':
    sys.exit(main())
