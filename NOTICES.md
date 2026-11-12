# Notices

This file says under which licences the archives of the releases of this repository are distributed, and what that
gives you. The scripts, workflows and recipe files of the repository itself are under the MIT licence, with the
exceptions listed in `LICENSE`. The licence texts this file refers to are in `licenses/`: `LGPL-3.0.txt`, `GPL-3.0.txt`
(which version 3 of the LGPL adds to) and `Apache-2.0.txt`.

## libmpv-2.dll for Windows (releases `libmpv-windows-*`)

Each release has one archive per architecture, `mpv-dev-x86_64-*.7z` and `mpv-dev-aarch64-*.7z`, laid out like
media-kit's: `libmpv-2.dll`, `libmpv.dll.a`, `include/mpv`, the licence texts of every library in `licenses/` (one
folder per library) and `BUILDINFO.txt`, which names every library with its commit or the SHA-256 of its archive.

### Licence

- **mpv** is built with `-Dgpl=false`, which leaves out the files that are GPL only: the library is under the GNU
  Lesser General Public License version 2.1 or later (mpv's `Copyright` file).
- **FFmpeg** is configured with `--disable-gpl --disable-nonfree --enable-version3`. Its code is LGPL version 2.1 or
  later; `--enable-version3` makes FFmpeg as built "LGPL version 3 or later", the version of the LGPL that can be
  combined with OpenSSL 3 (Apache-2.0), linked into the same file for HTTPS. media-kit's own archives are configured
  the same way.
- **The other libraries** linked into the DLL (below) are under the LGPL 2.1 or later or under permissive licences,
  all of which can be combined under version 3 of the LGPL.

So `libmpv-2.dll` is distributed under the GNU Lesser General Public License version 3 or later
(https://www.gnu.org/licenses/lgpl-3.0.html, which adds to the GPL version 3, https://www.gnu.org/licenses/gpl-3.0.html),
each part keeping its own licence and copyright. A program that uses the library only through mpv's C API, loading
`libmpv-2.dll` at run time as `media_kit` does, may be under any licence, as the LGPL allows.

### Your rights

- **Use another build of the library.** An app that ships `libmpv-2.dll` as a separate file lets its users replace it
  with their own build of mpv's library (client API 2), for example one made from the sources below with their
  changes.
- **Get the corresponding source.** Each release carries `<tag>-sources.tar.xz`: the sources of every library built
  for the DLL at the commits listed in `BUILDINFO-<arch>.txt`, the build recipe at its commit and the files of
  `windows/` that set the options of FFmpeg and mpv. Every library is built at the commit pinned in
  `windows/sources.lock`, so running the workflow again, or the same commands on a Linux machine with the container it
  names, rebuilds the DLL from the same code.

### Libraries built into the DLL

The recipe compiles these projects for the DLL (the list is that of the x64 build; arm64 has the same without the
NVIDIA headers). The linker keeps only the code that mpv and the enabled FFmpeg components reach, so some of them
(marked "build only") contribute nothing to the file; they are listed because their sources are part of the published
source archive.

| Project | Licence (SPDX) | Used for |
|---|---|---|
| mpv | LGPL-2.1-or-later (built with `-Dgpl=false`) | the player |
| FFmpeg | LGPL-2.1-or-later code, LGPL-3.0-or-later as configured | demuxing, decoding, network protocols, filters |
| libplacebo | LGPL-2.1-or-later | mpv's video renderer |
| FriBidi | LGPL-2.1-or-later | subtitle text direction |
| libsoxr | LGPL-2.1-or-later | audio resampling |
| libssh | LGPL-2.1-or-later | build only (SFTP protocol not enabled) |
| GNU libiconv | LGPL-2.1-or-later | character sets of subtitles |
| uchardet | MPL-1.1 OR GPL-2.0-or-later OR LGPL-2.1-or-later | subtitle encoding detection |
| libass | ISC | subtitles |
| FreeType | FTL OR GPL-2.0-or-later (used under the FTL) | fonts of subtitles |
| HarfBuzz | MIT | text shaping of subtitles |
| Fontconfig | MIT-style (Fontconfig `COPYING`) | font lookup |
| libunibreak | Zlib | line breaking of subtitles |
| Expat | MIT | Fontconfig configuration |
| Brotli | MIT | WOFF2 fonts, compression in OpenSSL |
| zlib-ng | Zlib | compression |
| bzip2 | bzip2-1.0.6 | compressed fonts in FreeType when present at its build (FFmpeg's bzlib is disabled) |
| Zstandard | BSD-3-Clause OR GPL-2.0-only (used under BSD-3-Clause) | compression in OpenSSL |
| libpng | libpng-2.0 | PNG glyphs of fonts |
| libjpeg-turbo | IJG AND BSD-3-Clause AND Zlib | JPEG screenshots |
| Little CMS 2 | MIT | colour management |
| OpenSSL | Apache-2.0 | HTTPS and TLS |
| dav1d | BSD-2-Clause | AV1 decoding |
| libxml2 | MIT | DASH manifests |
| Intel libvpl | MIT | Intel Quick Sync dispatch |
| libjxl | BSD-3-Clause | build only (JPEG XL not enabled) |
| Highway | Apache-2.0 OR BSD-3-Clause | build only (used by libjxl) |
| libwebp | BSD-3-Clause | build only (FFmpeg's own WebP decoder is used) |
| zimg, graphengine | WTFPL | build only (zscale filter not enabled) |
| libbs2b | MIT | build only (filter not enabled) |
| libmysofa | BSD-3-Clause | build only (filter not enabled) |
| Speex | BSD-3-Clause | build only (decoder not enabled) |
| Ogg, Vorbis, Opus (and its model data) | BSD-3-Clause | build only (FFmpeg's own decoders are used) |
| libmodplug | public domain | build only |
| SRT | MPL-2.0 | build only (protocol not enabled) |
| OpenAL Soft | LGPL-2.0-or-later | build only (OpenAL output disabled in mpv) |
| SDL2 | Zlib | FFmpeg's SDL output device |
| shaderc | Apache-2.0 | shader compilation for libplacebo |
| glslang | BSD-3-Clause, BSD-2-Clause, MIT, Apache-2.0 (glslang `LICENSE.txt`) | shader compilation |
| SPIRV-Tools | Apache-2.0 | shader compilation |
| SPIRV-Cross | Apache-2.0 | shader translation for Direct3D 11 |
| SPIRV-Headers | MIT | headers |
| Vulkan-Loader, Vulkan-Headers | Apache-2.0 | libplacebo's Vulkan support (mpv's Vulkan output disabled) |
| glad | MIT (generator) and Apache-2.0 (Khronos registry) | OpenGL loader of libplacebo |
| fast_float | Apache-2.0 OR BSL-1.0 OR MIT | number parsing in libplacebo |
| xxHash | BSD-2-Clause | hashing in libplacebo |
| ANGLE headers | BSD-3-Clause | EGL headers |
| AMF headers | MIT | AMD AMF, loaded at run time when present |
| nv-codec-headers | MIT | NVIDIA decoding, loaded at run time when present (x64) |
| AviSynth+ headers | GPL-2.0-or-later with a linking exception | build only (AviSynth not enabled) |
| mingw-w64 runtime and winpthreads | ZPL-2.1, MIT, BSD-3-Clause and public domain parts | C runtime start-up, threads |
| LLVM libc++, libunwind, compiler-rt | Apache-2.0 WITH LLVM-exception | C++ runtime |

### Credits some of these licences ask for

- Portions of this software are copyright © The FreeType Project (https://freetype.org). All rights reserved.
- This software is based in part on the work of the Independent JPEG Group.

An app that ships the DLL carries these two sentences in its documentation, its about box for example.

## libmpv for macOS (releases `libmpv-macos-*`)

Each release has the xcframeworks of libmpv and of the libraries it loads, arm64 and x86_64 in each, for macOS 12 and
later: all of them in one `.tar.gz`, and each in its own zip for Swift Package Manager. `BUILDINFO-macos.txt` names
every library with its version and the SHA-256 of its source archive.

### Licence

- **mpv** is built with `-Dgpl=false`: GNU LGPL version 2.1 or later.
- **FFmpeg** (`Avcodec`, `Avfilter`, `Avformat`, `Avutil`, `Swresample`, `Swscale`) is configured with
  `--enable-version3` and without `--enable-gpl` or `--enable-nonfree`: LGPL version 3 or later as built, the version
  of the LGPL that can be combined with Mbed TLS (Apache-2.0), which FFmpeg uses for HTTPS.
- **The other libraries** (below) are under the LGPL 2.1 or later or under permissive licences, all of which can be
  combined under version 3 of the LGPL.

So these frameworks are distributed under the GNU Lesser General Public License version 3 or later, each part keeping
its own licence and copyright. A program that uses them only through mpv's C API, opening `Mpv.framework/Mpv` at run
time as `media_kit` does, may be under any licence.

### Your rights

- **Use another build of the libraries.** The frameworks are separate files inside an app. They can be replaced by
  another build of the same libraries with the same framework names; macOS then asks for the app to be signed again
  (`codesign --force --deep --sign - <the app>`).
- **Get the corresponding source.** Each release carries `<tag>-sources.tar.xz`: the recipe at its commit with the
  files of `macos/` applied, and every source archive it builds from, each checked by the SHA-256 that
  `macos/packages.lock.nix` pins. Running the workflow again, or the recipe's `make` on a Mac with Nix and the Xcode
  named in `BUILDINFO-macos.txt`, rebuilds the frameworks from the same code. The licence texts of each library, as its
  sources hold them, are in `<tag>-licenses.tar.gz`.

### Libraries in the frameworks

| Framework | Project | Licence (SPDX) | Used for |
|---|---|---|---|
| `Mpv` | mpv | LGPL-2.1-or-later (built with `-Dgpl=false`) | the player |
| `Avcodec`, `Avfilter`, `Avformat`, `Avutil`, `Swresample`, `Swscale` | FFmpeg | LGPL-2.1-or-later code, LGPL-3.0-or-later as configured | demuxing, decoding (VideoToolbox on the GPU), network protocols, filters |
| `Placebo` | libplacebo | LGPL-2.1-or-later | mpv's video renderer |
| `Fribidi` | GNU FriBidi | LGPL-2.1-or-later | subtitle text direction |
| `Uchardet` | uchardet | MPL-1.1 OR GPL-2.0-or-later OR LGPL-2.1-or-later | subtitle encoding detection |
| `Ass` | libass | ISC | subtitles |
| `Freetype` | FreeType | FTL OR GPL-2.0-or-later (used under the FTL) | fonts of subtitles |
| `Harfbuzz` | HarfBuzz | MIT | text shaping of subtitles |
| `Png16` | libpng | libpng-2.0 | PNG glyphs of fonts |
| `Dav1d` | dav1d | BSD-2-Clause | AV1 decoding |
| `Xml2` | libxml2 | MIT | DASH manifests |
| `Mbedtls`, `Mbedx509`, `Mbedcrypto` | Mbed TLS | Apache-2.0 | HTTPS and TLS |
| none (built in) | fast_float | Apache-2.0 OR BSL-1.0 OR MIT | number parsing in libplacebo (header only) |
| none (built in) | Vulkan-Headers | Apache-2.0 OR MIT | headers of libplacebo's Vulkan stubs (Vulkan is off) |

### Credits some of these licences ask for

- Portions of this software are copyright © The FreeType Project (https://freetype.org). All rights reserved.

## libmpv for Android (releases `libmpv-android-*`)

Each release re-hosts, unchanged, the `default` flavour of media-kit/libmpv-android-video-build release `v1.1.7`: one
`default-<abi>.jar` per ABI (arm64-v8a, armeabi-v7a, x86, x86_64), each a zip of `lib/<abi>/libmpv.so` and
`lib/<abi>/libmediakitandroidhelper.so`, and `debug-symbols-default.zip`. `android/README.md` gives their SHA-256,
the commit of every library and what the files say about their build; `BUILDINFO-android.txt` on the release the
same.

### Licence

- **mpv** is built with `-Dgpl=false`: GNU LGPL version 2.1 or later.
- **FFmpeg** 6.0 is configured with `--disable-gpl --disable-nonfree --enable-version3`, and each of its libraries
  says `license: LGPL version 3 or later`: LGPL version 3 or later as built, the version that can be combined with
  Mbed TLS (Apache-2.0), which FFmpeg uses for HTTPS.
- **The other libraries** (below) are under the LGPL 2.1 or later or under permissive licences.

So `libmpv.so` is distributed under the GNU Lesser General Public License version 3 or later, each part keeping its own
licence and copyright. `libmediakitandroidhelper.so` is under the MIT licence of media-kit-android-helper. A program
that loads `libmpv.so` at run time and uses only mpv's C API, as `media_kit` does, may be under any licence.

### Your rights

- **Use another build of the library.** `libmpv.so` is a separate file in an app's package. It can be replaced by
  another build of mpv's library with the same name and ABI, for example one made from the source below with your
  changes, and the app's package rebuilt with it.
- **Get the corresponding source.** Each release carries `<tag>-sources.tar.xz`: the recipe at `v1.1.7` with its
  patches, and every library it builds into `libmpv.so` and the helper at the commit of `android/sources.lock`, and
  `android/build.sh`, which rebuilds the jars from that archive. mpv and FFmpeg are also attached alone. The licence
  texts of each library, as its source holds them, are in `<tag>-licenses.tar.gz`. The written offer of
  `android/README.md` covers the same source.

### Libraries in `libmpv.so`

| Project | Licence (SPDX) | Used for |
|---|---|---|
| mpv | LGPL-2.1-or-later (built with `-Dgpl=false`) | the player |
| FFmpeg | LGPL-2.1-or-later code, LGPL-3.0-or-later as configured | demuxing, decoding (MediaCodec on the device's hardware), network protocols, filters |
| FriBidi | LGPL-2.1-or-later | subtitle text direction |
| libass | ISC | subtitles |
| FreeType | FTL OR GPL-2.0-or-later (used under the FTL) | fonts of subtitles |
| HarfBuzz | MIT | text shaping of subtitles |
| dav1d | BSD-2-Clause | AV1 decoding |
| libxml2 | MIT | DASH manifests |
| Mbed TLS | Apache-2.0 | HTTPS and TLS |
| zlib (the NDK's) | Zlib | compression |

The libraries are linked statically into `libmpv.so`, which needs only Android's own libraries. The recipe's
`encoders-gpl` flavour (GPL, with libx264) is not built: nothing GPL is in these files.

### Credits some of these licences ask for

- Portions of this software are copyright © The FreeType Project (https://freetype.org). All rights reserved.
