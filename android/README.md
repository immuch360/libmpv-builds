# libmpv for Android

The `libmpv-android-*` releases of this repository re-host the libmpv that Flutter apps on Android get from
[media_kit](https://github.com/media-kit/media-kit): the `default` flavour of
[media-kit/libmpv-android-video-build](https://github.com/media-kit/libmpv-android-video-build), release `v1.1.7`, the
archives `media_kit_libs_android_video` 1.3.8 downloads. They are not rebuilt here. Each release carries the
unchanged files of that release, checked by their SHA-256, with their corresponding source fetched from each project
at the commit the recipe built, the licence texts, and a script that rebuilds them from that source.

The Meta Quest build of [Immuch360](https://github.com/freeKC/Immuch360) ships the arm64 archive from its release 46.

## Provenance

The release `v1.1.7` of media-kit/libmpv-android-video-build was published on 4 October 2025 at 13:26 UTC from the
tag `v1.1.7`, commit `fe8c3ac1a91c09aa6fb1deccbc833f1bafa54768` (committed 27 minutes before). The recipe's workflow
(`.github/workflows/build.yaml`) builds `buildscripts/bundle_default.sh` on `ubuntu-22.04` at each push to `main` and
uploads the files to a draft release, which the maintainers publish under a tag. GitHub no longer keeps the log of
that run, so what the files were built with was read from the files themselves (below).

| File | Bytes | SHA-256 (as GitHub lists it and as downloaded on 12 November 2026) |
|---|---:|---|
| `default-arm64-v8a.jar` | 5,729,978 | `4363dfa5d3d415b91c1f16f6fb90c3fe59a77dfd3f9b824d2b24b492d6b09df9` |
| `default-armeabi-v7a.jar` | 5,499,353 | `8ead114fc5a43348d89dc0eb8f41823e549b15115c29f73ee26973f973620995` |
| `default-x86.jar` | 5,839,220 | `94c13cb6188b774710e5e487afff6e500c4af504df74b2494d7b12cf9be8a66a` |
| `default-x86_64.jar` | 6,516,632 | `90268cd15f0766e07fb8e427388c621161177c9eb343c544f327bd63232bb236` |
| `debug-symbols-default.zip` | 144,994,685 | `4b2e5a007112897015880a498cafb442aef67b482f588c6da73bc80c6dca24df` |

Each jar is a zip of two libraries for one ABI:

| Library | arm64-v8a | armeabi-v7a | x86 | x86_64 | What |
|---|---:|---:|---:|---:|---|
| `libmpv.so` | 12,369,680 | 11,746,532 | 13,172,484 | 15,816,336 | mpv's library with FFmpeg and the libraries below linked in statically, stripped |
| `libmediakitandroidhelper.so` | 386,696 | 286,812 | 350,252 | 367,528 | the JNI helper of media_kit (MIT): the Java VM for FFmpeg's MediaCodec decoders |

`debug-symbols-default.zip` holds `prefix/<abi>/lib` of the build: the unstripped `libmpv.so` and the static
libraries, headers and pkg-config files it was linked from.

Read from the arm64 `libmpv.so` (the other three say the same, but for the ABI):

- `mpv v0.36.0-549-g78d43740f5-dirty`: mpv at commit `78d43740f5`, with the recipe's patch applied (hence `dirty`),
  configured with `-Dgpl=false -Dlibmpv=true -Dlua=disabled -Dcplayer=false -Diconv=disabled -Dvulkan=disabled
  -Dlibplacebo=disabled -Dmanpage-build=disabled`.
- `FFmpeg version n6.0`, configured with `--disable-gpl --disable-nonfree --enable-version3`, then
  `--enable-mbedtls --enable-libdav1d --enable-libxml2 --enable-jni --enable-mediacodec`, every decoder, demuxer,
  parser, protocol and filter disabled but those `buildscripts/flavors/default.sh` lists. Each FFmpeg library reports
  `license: LGPL version 3 or later`.
- `Shaper: FriBidi 1.0.12 ... HarfBuzz-ng`: libass with FriBidi and HarfBuzz.
- zlib 1.2.12 (its `inflate` and `deflate` strings), linked statically: the recipe builds no zlib, so it is the one
  of the NDK's sysroot, which FFmpeg's configure finds there.
- Built by the NDK r25c (`.note.android.ident`: build 9519653) for API level 21. The helper was built by clang 17.0.2
  of a later NDK (Android build 10552028). Both need only Android's own libraries (`libc`, `libm`, `libdl`,
  `libandroid`, `liblog`, `libEGL`, `libOpenSLES`).

## Nothing GPL inside

A libmpv with GPL parts could not be offered under the LGPL. These files have none:

- FFmpeg: `--disable-gpl` and `--disable-nonfree` in the configuration string each `libmpv.so` carries, no
  `--enable-gpl`, no `--enable-libx264` or `--enable-libx265`, and every FFmpeg library's licence string says
  `LGPL version 3 or later` (FFmpeg writes `GPL` there when built with `--enable-gpl`). The `x264` strings in the
  library are those of FFmpeg's H.264 decoder, which reads the version an x264 encoder writes into a stream, and of
  mpv's option `vd-lavc-assume-old-x264`; there is no x264 or x265 symbol.
- mpv: `-Dgpl=false` in the configuration string it carries.
- The recipe: its `default` flavour (`buildscripts/bundle_default.sh`, the only one its workflow runs at that tag)
  links FFmpeg with mbedtls, dav1d and libxml2, and mpv with FFmpeg and libass (`include/depinfo.sh` without
  `ENCODERS_GPL`). Its `encoders-gpl` flavour, under the GPL, adds libx264 and libvpx and is commented out of the
  workflow. `include/download-deps.sh` clones libx264, libvpx, libogg, libvorbis, fftools-ffi and media_kit at their
  heads too, but the default flavour builds none of them; they are not part of these files nor of the source archive.

To check a file yourself:

```sh
unzip -p default-arm64-v8a.jar lib/arm64-v8a/libmpv.so > libmpv.so
strings libmpv.so | grep -E '^lib[a-z]+ license: '          # LGPL version 3 or later, six lines
strings libmpv.so | grep -c -- '--disable-gpl --disable-nonfree --enable-version3'
strings libmpv.so | grep -E '^-Dgpl=false '
```

## The source

`sources.lock` names every tree the default flavour builds, with the ref the recipe clones and the commit it resolved
to on 12 November 2026. mpv and the helper are cloned by commit. Each tag is older than the release and names a
release of its project; mpv's and FFmpeg's own version strings in the library (`g78d43740f5`, `n6.0` without a
commit count) and FriBidi's (`1.0.12`) name the same code.

| Tree | Repository | Ref | Commit | Licence (SPDX) |
|---|---|---|---|---|
| recipe | media-kit/libmpv-android-video-build | `v1.1.7` | `fe8c3ac1a9` | MIT for the `default` flavour (its `LICENSE`) |
| mpv | mpv-player/mpv | commit | `78d43740f5` | LGPL-2.1-or-later as built (`-Dgpl=false`) |
| ffmpeg | FFmpeg/FFmpeg | `n6.0` | `ea3d24bbe3` | LGPL-2.1-or-later code, LGPL-3.0-or-later as configured |
| mbedtls | Mbed-TLS/mbedtls | `v3.4.0` | `1873d3bfc2` | Apache-2.0 |
| dav1d | videolan/dav1d (code.videolan.org) | `1.2.0` | `676a864a11` | BSD-2-Clause |
| libxml2 | GNOME/libxml2 (gitlab.gnome.org) | `v2.10.3` | `f507d167f1` | MIT |
| freetype | freetype/freetype (gitlab.freedesktop.org) | `VER-2-13-0` | `de8b92dd7e` | FTL OR GPL-2.0-or-later, used under the FTL |
| fribidi | fribidi/fribidi | `v1.0.12` | `6428d8469e` | LGPL-2.1-or-later |
| harfbuzz | harfbuzz/harfbuzz | `7.2.0` | `a321c4fee5` | MIT |
| libass | libass/libass | `0.17.1` | `e8ad72accd` | ISC |
| media-kit-android-helper | media-kit/media-kit-android-helper | commit | `42054e5d47` | MIT |

The recipe patches two of them before the build, with the files of its `buildscripts/patches/`:
`ffmpeg/dash_base_url_escape.patch`, `ffmpeg/hls_mp4_seek.patch` and `mpv/mpv_lavc_set_java_vm.patch`. The archive
keeps each tree as its project published it, and the patches in `recipe/`.

A release carries:

| File | Content |
|---|---|
| the five files above | unchanged, the same bytes as media-kit's release |
| `<tag>-sources.tar.xz` | `recipe/` (the recipe at `v1.1.7`, with its patches), `deps/<name>/` (each tree of the lock at its commit), `android/` (this folder) and `SOURCES.txt` |
| `mpv-78d43740f5-source.tar.xz`, `ffmpeg-n6.0-source.tar.xz` | mpv and FFmpeg alone, the same trees as in the archive |
| `<tag>-licenses.tar.gz` | the licence files of every tree, as its source holds them |
| `BUILDINFO-android.txt` | the provenance above, the pins and what the files say about their build |
| `SHA256SUMS.txt` | the SHA-256 of every other file of the release |

`fetch_sources.sh archive <dir> <tag>` makes the three source files and the licences from the lock, and stops if a
ref no longer resolves to its commit. The archives have a fixed order, owner and time.

## Rebuild

`build.sh <tag>-sources.tar.xz <work dir>` rebuilds the four jars from the source archive, with the steps of the
recipe's `bundle_default.sh` and of its workflow: the Android SDK packages, the patches, the default FFmpeg options,
the build of each ABI, the strip, then the helper with Gradle and the jars. It needs the host the recipe's workflow
used (Ubuntu 22.04 x86_64, JDK 17, an Android SDK with NDK 25.2.9519653 and 27.3.13750724, meson, ninja, nasm). The
result is not the same bytes, since the zip times and the build paths written
into FFmpeg's configuration string differ; the script prints the licence and configuration strings to compare. It is
not run by this repository's workflows.

## Licences

`libmpv.so` is distributed under the **GNU Lesser General Public License version 3 or later** as a whole
(`licenses/LGPL-3.0.txt`, which adds to `licenses/GPL-3.0.txt`): FFmpeg configured with `--enable-version3` is LGPL
version 3 or later, the version of the LGPL that can be combined with Mbed TLS (Apache-2.0); mpv and FriBidi are
LGPL 2.1 or later, and the other libraries permissive (the table above, zlib under the Zlib licence). Each part keeps
its own licence and copyright. `libmediakitandroidhelper.so` is under the MIT licence of media-kit-android-helper.

An app loads `libmpv.so` at run time (`System.loadLibrary`, `dlopen`), as media_kit does, so it may be under any
licence. Its users may replace the library with their own build of the same name and ABI; on Android that means
rebuilding the app package with it, which the source and the scripts here allow.

The scripts of this folder are under the MIT licence of the repository (`LICENSE`).

### Written offer

The complete corresponding source of the libraries in a `libmpv-android-*` release is on that release, under the same
tag. For at least three years after the last distribution of a build that carries one of them, FreeKC will also
provide it to anyone who asks through an issue of https://github.com/immuch360/libmpv-builds, on a medium customarily
used for software interchange, for no more than the cost of physically performing the distribution.
