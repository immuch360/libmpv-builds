# Changelog

The versions of this file are those of the recipe. The archives have releases of their own, tagged
`libmpv-windows-<date>-<run number>` and `libmpv-macos-<date>-<run number>`, whose `BUILDINFO` files name the commit
of the recipe that built them, and `libmpv-android-<date>-<number>` (re-hosted, `android/README.md`).

## 1.2.0 (2026-11-13)

- Windows and macOS: FFmpeg's Dolby TrueHD and MLP decoders and the MLP parser, and on Windows the PGS subtitle
  decoder (macOS had it). The `truehd` demuxer was already in, so mpv opened a TrueHD track and played it silent
  ("ad: Failed to initialize a decoder for codec 'truehd'"): the default track of most UHD Blu-ray remuxes. PGS
  subtitles of Blu-ray discs showed nothing ("Could not find subtitle decoder for format 'hdmv_pgs_subtitle'"). All
  three are LGPL parts of FFmpeg; the archives stay LGPL-3.0-or-later. Found by the Plex validation of Immuch360
  Desktop build 26 (13 November 2026).
- Android: unchanged. The re-hosted media-kit v1.1.7 build has no TrueHD decoder; adding one means building the jars
  from `android/build.sh` with a changed flavour, not a re-host.
- `tests/test_recipe.py`: the decoders of the Windows configuration, and the TrueHD lines of the macOS one.

## 1.1.0 (2026-11-12)

- Android: `android/` and the `libmpv-android-*` releases. They re-host the four `default-<abi>.jar` and the debug
  symbols of media-kit/libmpv-android-video-build `v1.1.7` (commit `fe8c3ac1`), unchanged and checked by their
  SHA-256, with their corresponding source: `android/sources.lock` pins the recipe, mpv `78d43740`, FFmpeg `n6.0`,
  Mbed TLS, dav1d, libxml2, FreeType, FriBidi, HarfBuzz, libass and media-kit-android-helper to commits, and
  `android/fetch_sources.sh` archives them. `android/build.sh` rebuilds the jars from that archive (not run by the
  workflows). Checked in the files: FFmpeg `--disable-gpl --disable-nonfree --enable-version3`, licence strings
  `LGPL version 3 or later`, mpv `-Dgpl=false`, no x264 or x265. First release: `libmpv-android-20261112-1`.
- `tests/test_recipe.py`: the Android lock and scripts.
- `NOTICES.md`: libmpv for Android.

## 1.0.0 (2026-11-10)

The recipe as used for Immuch360 Desktop build 24, moved with its history from
[freeKC/Immuch360](https://github.com/freeKC/Immuch360) (`.github/workflows/immuch360-libmpv.yml`,
`.github/desktop/libmpv/` and `.github/desktop/libmpv-macos/`) into a repository of its own. That build of the app
plays video with the archives of `libmpv-windows-20261009-3` and `libmpv-macos-20261102-12` of freeKC/Immuch360.

- Windows x64 and arm64: Predidit/libmpv-win32-video-cmake at `fdf75129`, with `windows/ffmpeg.cmake` and
  `windows/mpv.cmake` over it; FFmpeg `5b9a3ad7` (n9.1-dev-1261), mpv `0b7ed670`; every other library at its commit in
  `windows/sources.lock`; the Arch Linux build container pinned by its digest.
- macOS 12 and later, arm64 and x86_64: media-kit/libmpv-darwin-build at `aadae8ce`, with the files of `macos/` over
  it; FFmpeg and mpv at the commits of the Windows build, libplacebo added, the y4m demuxer and the rawvideo decoder
  enabled; every source archive pinned by its SHA-256; Xcode 16.4.
- Changes made by the move: the workflow is `.github/workflows/build.yml`; the container package is
  `ghcr.io/immuch360/libmpv-build`, filled from the public copy `ghcr.io/freekc/libmpv-build` when shinchiro's
  registry no longer has the pinned digest; the Windows release is the latest release of the repository and neither
  release is a pre-release; the summary of a release prints the base address of the releases with the CMake lines;
  pull requests that change the recipe build and check it, and there is no schedule.
- The checks of the app that guarded the recipe, ported to `tests/test_recipe.py` and run by `checks.yml`.
- Licences: the repository under MIT, with the exceptions listed in `LICENSE`; `NOTICES.md` for the archives.
