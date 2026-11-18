# The licences of the FFmpeg program of Immuch360

This archive holds `ffmpeg` and `ffprobe` of [FFmpeg](https://ffmpeg.org) with their shared libraries, built by the CI
of [immuch360/libmpv-builds](https://github.com/immuch360/libmpv-builds) (`.github/workflows/ffmpeg.yml`,
`ffmpeg/build.py`) from the sources pinned in `ffmpeg/sources.lock`. Immuch360 Desktop downloads it when the user asks
for it and runs it as a separate program: it decodes videos to raw frames on a pipe and encodes raw frames from a pipe.
In `licenses/` are the texts of the code it is made of.

FFmpeg was configured with `--disable-gpl --disable-nonfree` and without `--enable-version3`: the program and its
libraries are under the **GNU Lesser General Public License version 2.1 or later** as a whole. The configure line is
in `BUILD-INFO.txt`; `ffmpeg -buildconf` and `ffmpeg -L` print it and the licence too.

| Code | Where | Licence | Text in the archive |
|---|---|---|---|
| FFmpeg (libavcodec, libavformat, libavfilter, libavdevice, libavutil, libswscale, libswresample, `ffmpeg`, `ffprobe`) | https://ffmpeg.org, the release tarball of `sources.lock`, its commit in `BUILD-INFO.txt` | LGPL-2.1-or-later, with some files under MIT, BSD or ISC style licences (its `LICENSE.md`) | `FFmpeg-COPYING.LGPLv2.1.txt`, `FFmpeg-LICENSE.md` |
| The inverse DCT of the Independent JPEG Group in FFmpeg (`libavcodec/jrevdct.c`) | FFmpeg | IJG terms: this software is based in part on the work of the Independent JPEG Group | `FFmpeg-IJG.txt` (the header of the file) |
| zimg, the scaler and colour converter of the `zscale` filter (tone mapping) | https://github.com/sekrit-twc/zimg, release 3.0.6, static library | WTFPL | `zimg-COPYING.txt` |
| SVT-AV1, the AV1 encoder (`libsvtav1`) | https://gitlab.com/AOMediaCodec/SVT-AV1, v3.1.2, static library | BSD 3-Clause Clear (files of v0.8.7 and before: BSD 2-Clause), with the Alliance for Open Media Patent License 1.0 | `SVT-AV1-LICENSE.md`, `SVT-AV1-LICENSE-BSD2.md`, `SVT-AV1-PATENTS.md` |
| FAST corner detector and safestringlib, inside SVT-AV1 | `third_party/fastfeat`, `third_party/safestringlib` of SVT-AV1 | BSD 3-Clause; MIT | `SVT-AV1-fastfeat-LICENSE.txt`, `SVT-AV1-safestringlib-LICENSE.txt` |
| dav1d, the AV1 decoder (`libdav1d`) | https://code.videolan.org/videolan/dav1d, 1.5.5, static library | BSD 2-Clause | `dav1d-COPYING.txt` |
| `x86inc.asm` of the x264 project, part of dav1d | `src/ext/x86/x86inc.asm` of dav1d | ISC | `dav1d-x86inc-ISC.txt` (its header) |
| zlib | https://zlib.net, 1.3.2, static library | zlib licence | `zlib-LICENSE.txt` |
| libva and libva-drm (Linux archive only) | https://github.com/intel/libva, 2.24.1, shared libraries in `lib/` | MIT | `libva-COPYING.txt` |
| immuch360-run, the launcher of the Linux archive | `launcher/immuch360_run.c` of https://github.com/immuch360/av2-companion at the commit of `sources.lock` | MIT | `immuch360-run-MIT.txt` |
| The GCC runtime (libgcc, libstdc++) and the mingw-w64 runtime with winpthreads (Windows archive only), linked in statically | Debian 12 packages of the mingw-w64 cross compiler, in the build container named by its digest in `BUILD-INFO.txt` | GPL-3.0-or-later with the GCC Runtime Library Exception 3.1, which lets code compiled with GCC be distributed under any licence; mingw-w64: ZPL 2.1 and public domain parts, winpthreads MIT and BSD | `mingw-gcc-runtime-copyright.txt`, `mingw-w64-runtime-copyright.txt` (the copyright files of those packages) |

Nothing under the GPL or a non free licence is built in: the CI refuses a configuration with `--enable-gpl`,
`--enable-nonfree` or `--enable-version3`, any of libx264, libx265, libfdk, OpenH264, NVENC, AMF or QSV, a `config.h`
without `CONFIG_GPL 0` and `CONFIG_NONFREE 0`, an `ffmpeg -L` that does not name the LGPL 2.1 or later, a list of
encoders, decoders, formats, filters, bitstream filters or protocols other than that of `sources.lock`, and a program or
library that loads anything but the system's libraries and the archive's own. Every text of this folder is compared with
the file of the sources it comes from at each build.

The corresponding source (LGPL 2.1, section 6) is offered from the same place as this archive: `FFmpeg-SOURCE.txt`
gives the address of the sources asset of the release and the commits. Patents: `PATENTS-NOTE.md`.
