# Changelog

The versions of this file are those of the recipe. The archives have releases of their own, tagged
`libmpv-windows-<date>-<run number>` and `libmpv-macos-<date>-<run number>`, whose `BUILDINFO` files name the commit
of the recipe that built them.

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
