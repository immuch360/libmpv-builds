# libmpv builds

[![Build](https://github.com/immuch360/libmpv-builds/actions/workflows/build.yml/badge.svg)](https://github.com/immuch360/libmpv-builds/actions/workflows/build.yml)
[![Checks](https://github.com/immuch360/libmpv-builds/actions/workflows/checks.yml/badge.svg)](https://github.com/immuch360/libmpv-builds/actions/workflows/checks.yml)
[![Windows release](https://img.shields.io/github/v/release/immuch360/libmpv-builds?filter=libmpv-windows-*&label=windows&display_name=tag)](https://github.com/immuch360/libmpv-builds/releases)
[![macOS release](https://img.shields.io/github/v/release/immuch360/libmpv-builds?filter=libmpv-macos-*&label=macos&display_name=tag)](https://github.com/immuch360/libmpv-builds/releases)
[![Android release](https://img.shields.io/github/v/release/immuch360/libmpv-builds?filter=libmpv-android-*&label=android&display_name=tag)](android/README.md)
[![Recipe licence: MIT](https://img.shields.io/badge/recipe-MIT-blue)](LICENSE)
[![Archives: LGPL-3.0-or-later](https://img.shields.io/badge/archives-LGPL--3.0--or--later-blue)](NOTICES.md)

Reproducible builds of libmpv, mpv's player library with FFmpeg, for Windows x64 and arm64 and for macOS. Every
library is built from a pinned commit or a pinned archive, and every release carries its SHA-256 sums, the licence
texts and the corresponding source. The archives drop into Flutter apps that play video with
[media_kit](https://github.com/media-kit/media-kit).

For Android, the `libmpv-android-*` releases re-host media-kit's own libmpv (libmpv-android-video-build `v1.1.7`,
the archives `media_kit_libs_android_video` downloads) with its corresponding source, fetched at the commits it was
built from, and a script that rebuilds it: [android/README.md](android/README.md).

These builds play the videos of [Immuch360](https://github.com/freeKC/Immuch360) Desktop
([immuch360.com](https://immuch360.com)), where the recipe was first written.

## Why

`media_kit_libs_windows_video` downloads media-kit's libmpv archive of 21 October 2024, with FFmpeg N-117622. Its
recipe, media-kit/libmpv-win32-video-cmake, switched to an audio only configuration in December 2025 and no longer
builds video. FFmpeg has shipped security fixes since then. An app that opens files and streams it does not control
(photo libraries, media servers, network shares, downloads) needs those fixes in the libmpv it ships.

This repository rebuilds media_kit's video configuration with a current FFmpeg, from sources pinned so that a run
builds known code, and publishes the result with everything the licences ask for.

The current defaults build FFmpeg at commit `5b9a3ad7` (n9.1-dev-1261) and mpv at commit `0b7ed670`, the master
branches that the Windows recipe built green in September 2026, with LLVM 22 for the Windows cross compilation.

## What a release contains

A Windows release is tagged `libmpv-windows-<date>-<run number>`:

| File | Content |
|---|---|
| `mpv-dev-x86_64-<date>-git-<mpv>.7z` | `libmpv-2.dll`, `libmpv.dll.a`, `include/mpv`, `licenses/`, `BUILDINFO.txt`, laid out like media-kit's archives |
| `mpv-dev-aarch64-<date>-git-<mpv>.7z` | the same for Windows on Arm |
| `BUILDINFO-x86_64.txt`, `BUILDINFO-aarch64.txt` | the run, the recipe and its commit, the container digest, the mpv and FFmpeg commits, every library with its commit or SHA-256 |
| `<tag>-sources.tar.xz` | the corresponding source: every library at its commit, the recipe, the files of `windows/` |
| `SHA256SUMS.txt` | the SHA-256 of the two archives and of the source |

A macOS release is tagged `libmpv-macos-<date>-<run number>`:

| File | Content |
|---|---|
| `libmpv-xcframeworks_<tag>_macos-universal-video-default.tar.gz` | every xcframework, arm64 and x86_64 in each, for macOS 12 and later |
| `libmpv-xcframeworks_<tag>_macos-universal-video-default_<Name>.zip` | one zip per xcframework (`Mpv`, `Avcodec`, `Placebo` and the others), the binary targets of Swift Package Manager |
| `BUILDINFO-macos.txt` | the run, the recipe and its commit, Xcode and Nix, every source archive with its SHA-256, what the checks read |
| `<tag>-sources.tar.xz`, `<tag>-licenses.tar.gz` | the corresponding source, and the licence texts of every library |
| `SHA256SUMS.txt` | the SHA-256 of every file of the release |

An Android release is tagged `libmpv-android-<date>-<number>`: media-kit's four `default-<abi>.jar` and their debug
symbols, unchanged, with `<tag>-sources.tar.xz`, the mpv and FFmpeg sources alone, `<tag>-licenses.tar.gz`,
`BUILDINFO-android.txt` and `SHA256SUMS.txt` ([android/README.md](android/README.md)).

The Windows release is marked as the latest release of the repository; the macOS and Android ones never are.

Before a macOS release, the workflow checks the frameworks on the runner: no function looked up at run time that no
library defines, and a y4m video read from a file and over HTTP with exact seeks, on each architecture the runner can
run.

## Pin a release in a Flutter app

### Windows

`media_kit_libs_windows_video` downloads its libmpv archive in `windows/CMakeLists.txt`. Since that package comes
from pub.dev, the app keeps a copy of it in its own repository and uses it through `dependency_overrides`:

```yaml
# pubspec.yaml of the app
dependency_overrides:
  media_kit_libs_windows_video:
    path: packages/media_kit_libs_windows_video
```

In that copy, a switch picks the archive. With `IMMUCH360_LIBMPV_FROM_CI` on, the package downloads an archive of
this repository, pinned by its release tag and its SHA-256; off, media-kit's archive of 2024. The run that publishes
a release prints the `set(...)` lines in its summary, so a new pin is one paste:

```cmake
# Printed by the run that published the release (its summary, "Lines for the CMakeLists.txt that pins the release")
set(IMMUCH360_LIBMPV_RELEASES "https://github.com/immuch360/libmpv-builds/releases/download")
set(IMMUCH360_LIBMPV_TAG "libmpv-windows-<date>-<run>")
set(IMMUCH360_LIBMPV_X64 "mpv-dev-x86_64-<date>-git-<mpv>.7z")
set(IMMUCH360_LIBMPV_X64_SHA256 "<SHA-256 from SHA256SUMS.txt>")
set(IMMUCH360_LIBMPV_ARM64 "mpv-dev-aarch64-<date>-git-<mpv>.7z")
set(IMMUCH360_LIBMPV_ARM64_SHA256 "<SHA-256 from SHA256SUMS.txt>")

# On by default; the environment variable of the same name overrides it for one build
if(DEFINED ENV{IMMUCH360_LIBMPV_FROM_CI})
  set(IMMUCH360_LIBMPV_FROM_CI "$ENV{IMMUCH360_LIBMPV_FROM_CI}")
elseif(NOT DEFINED IMMUCH360_LIBMPV_FROM_CI)
  set(IMMUCH360_LIBMPV_FROM_CI ON)
endif()

if(FLUTTER_TARGET_PLATFORM STREQUAL "windows-x64")
  set(LIBMPV_CI "${IMMUCH360_LIBMPV_X64}")
  set(LIBMPV_CI_SHA256 "${IMMUCH360_LIBMPV_X64_SHA256}")
else()
  set(LIBMPV_CI "${IMMUCH360_LIBMPV_ARM64}")
  set(LIBMPV_CI_SHA256 "${IMMUCH360_LIBMPV_ARM64_SHA256}")
endif()

if(IMMUCH360_LIBMPV_FROM_CI)
  set(LIBMPV "${LIBMPV_CI}")
  set(LIBMPV_SHA256 "${LIBMPV_CI_SHA256}")
  set(LIBMPV_URL "${IMMUCH360_LIBMPV_RELEASES}/${IMMUCH360_LIBMPV_TAG}/${LIBMPV}")
else()
  # media-kit's archive of 2024: LIBMPV, LIBMPV_SHA256 and LIBMPV_URL as the upstream package sets them
endif()

# SHA-256 rather than the MD5 of the upstream package
file(DOWNLOAD "${LIBMPV_URL}" "${CMAKE_BINARY_DIR}/${LIBMPV}"
  EXPECTED_HASH SHA256=${LIBMPV_SHA256} TLS_VERIFY ON STATUS LIBMPV_DOWNLOAD)
```

The rest of the package stays as it is: the archive has the layout of media-kit's, so the package extracts it, moves
`include/mpv` to `include` and bundles `libmpv-2.dll` next to the executable as before. Immuch360 keeps such a copy,
with a download that is tried again after a pause, in `mobile/packages/media_kit_libs_windows_video`.

### macOS

`media_kit_libs_macos_video` links its frameworks as binary targets of Swift Package Manager, each checked by its
SHA-256. Its `Package.swift` takes the three values the publishing run prints in its summary:

```swift
// Printed by the run that published the release (its summary, "Lines for the Package.swift that pins the release")
let libmpvTag = "libmpv-macos-<date>-<run>"
let libmpvArtifactBase = "https://github.com/immuch360/libmpv-builds/releases/download/\(libmpvTag)/libmpv-xcframeworks_<tag>_macos-universal-video-default"
let libmpvChecksums: [String: String] = [
    "Mpv": "<SHA-256>",
    "Avcodec": "<SHA-256>",
    // ... one line per framework
]

let libmpvTargets = libmpvChecksums.keys.sorted()

let package = Package(
    name: "media_kit_libs_macos_video",
    platforms: [.macOS("10.9")],
    products: [
        .library(name: "media-kit-libs-macos-video", targets: ["media_kit_libs_macos_video"] + libmpvTargets),
        .library(name: "Mpv", targets: ["Mpv"]),
    ],
    targets: libmpvTargets.map { framework in
        .binaryTarget(name: framework, url: "\(libmpvArtifactBase)_\(framework).zip",
                      checksum: libmpvChecksums[framework]!)
    } + [
        .target(name: "media_kit_libs_macos_video",
                dependencies: libmpvTargets.map { .target(name: $0) })
    ]
)
```

`Placebo.framework` is new compared with media-kit's frameworks: mpv needs libplacebo since 0.37. The frameworks are
built for macOS 12 and later. Immuch360 keeps this package in `mobile/packages/media_kit_libs_macos_video`.

## Rebuild with a newer FFmpeg

On Windows, FFmpeg and mpv are inputs of the workflow, so an FFmpeg security release is one dispatch:

```sh
gh workflow run build.yml --repo immuch360/libmpv-builds -f systems=windows -f ffmpeg_ref=<commit or tag>
```

The run builds, then publishes a new `libmpv-windows-*` release. To make the new commit the default, change
`ffmpeg_ref` and the `FFMPEG_REF` line of `.github/workflows/build.yml` together.

On macOS, FFmpeg is an archive pinned by its SHA-256 in `macos/packages.lock.nix`: change its `version`, `url` and
`sha256` there in the same commit as the Windows default, then dispatch with `systems` set to `macos` (or `both`).
`tests/test_recipe.py` fails when the two systems point at different FFmpeg or mpv commits.

| Input | Default | What it does |
|---|---|---|
| `recipe_repository` | `Predidit/libmpv-win32-video-cmake` | the Windows build recipe |
| `recipe_ref` | `fdf75129…` | its full commit; the toolchain cache is keyed by it |
| `ffmpeg_ref` | `5b9a3ad7…` | FFmpeg commit or tag (Windows) |
| `mpv_ref` | `0b7ed670…` | mpv commit or tag (Windows) |
| `sources` | `pinned` | `pinned`: the commits of `windows/sources.lock`; `heads`: the head of every library, never published |
| `publish` | `true` | publish the releases; otherwise the archives stay artifacts of the run |
| `systems` | `both` | `both`, `windows` or `macos` |
| `macos_recipe_ref` | `aadae8ce…` | full commit of media-kit/libmpv-darwin-build |
| `macos_target` | `mk-out-archive-xcframeworks-macos-universal-video-default` | the Nix package to build; only the default is published |

There is no schedule: the owner decides when to rebuild. A pull request that changes the recipe builds and checks
both systems and publishes nothing.

## How the pinning works

- **The Windows recipe.** Predidit/libmpv-win32-video-cmake, the fork of media-kit's recipe that still builds video,
  is checked out at a full commit. `windows/ffmpeg.cmake` and `windows/mpv.cmake` are copied over it: media_kit's
  video configuration, FFmpeg and mpv at the input commits, without the fork's own patches (one of them turns TLS
  certificate verification off by default), and without libarchive.
- **Every other library.** The recipe would clone the head of each branch on the day of the run. `windows/sources.lock`
  pins every git package to a commit, and `windows/pin_sources.sh` checks each one out after the recipe's download
  step. A package without a pin stops the run, with the line to add. Packages that come as archives are pinned by the
  recipe's own SHA-256. A dispatch with `sources` set to `heads` prints the lock lines of the current heads in its
  summary, for a review before the lock moves; it never publishes.
- **The container.** The recipe builds in shinchiro's Arch Linux image, whose registry keeps only the newest image, so
  a digest is gone within a day or two. The workflow pins a digest and copies it once into this repository's package,
  `ghcr.io/immuch360/libmpv-build`, with the same digest; every build job pulls it from there. The digest pinned today
  comes from the public copy `ghcr.io/freekc/libmpv-build`, which the image job reads when shinchiro's registry no
  longer has it. When the digest is nowhere, the run stops in its first minute and says how to pin a new one.
- **The tools.** Meson comes from PyPI, checked by the hashes of `windows/meson-requirements.txt`. Every action is
  pinned by its commit.
- **macOS.** media-kit/libmpv-darwin-build, a Nix build, is checked out at a full commit with the files of `macos/`
  over it (`macos/apply_overlay.sh`). `macos/packages.lock.nix` pins every source archive by its SHA-256, FFmpeg, mpv,
  libplacebo, fast_float and the Vulkan headers at the commits of the Windows build. The overlay refuses a recipe whose
  FFmpeg `meson.build` is not the one its copy was made from. Xcode 16.4 is pinned.
- **The checks.** `tests/test_recipe.py` runs on every push and pull request (workflow `checks.yml`, a few seconds):
  the lock format, `pin_sources.sh` on a test repository, the macOS pins against the Windows ones, the overlay on a
  test recipe, the release rules, and the y4m check on its fixtures.

```sh
python3 -m unittest discover -s tests -v
```

## Time on hosted runners

Measured on the runs of October and November 2026, on standard GitHub runners (4 processors), which cost no minutes
on a public repository:

| Part | Time |
|---|---|
| LLVM and mingw-w64, when not in the cache | 79 to 113 minutes |
| libmpv, each Windows architecture, in parallel | 28 to 50 minutes |
| macOS universal build, beside the Windows jobs | 8 to 11 minutes |
| A whole run from a cold cache | about 2.5 hours |
| A whole run with the toolchain cached | about 45 minutes |

The toolchain is cached by recipe commit and toolchain pins, and a cache entry unused for a week is dropped. Every
job stays under the 6 hour limit of hosted jobs.

## Credits

- [mpv](https://mpv.io) and [FFmpeg](https://ffmpeg.org), and the authors of every library listed in `NOTICES.md`.
- [shinchiro/mpv-winbuild-cmake](https://github.com/shinchiro/mpv-winbuild-cmake), the Windows cross compilation
  recipe with LLVM and mingw-w64, and shinchiro's Arch Linux build image.
- [media-kit/libmpv-win32-video-cmake](https://github.com/media-kit/libmpv-win32-video-cmake), its video configuration
  for media_kit, and [Predidit/libmpv-win32-video-cmake](https://github.com/Predidit/libmpv-win32-video-cmake), the
  fork that keeps it building.
- [media-kit/libmpv-darwin-build](https://github.com/media-kit/libmpv-darwin-build), the macOS Nix recipe.
- [media-kit/libmpv-android-video-build](https://github.com/media-kit/libmpv-android-video-build), the Android recipe
  and the builds the Android releases re-host, and
  [media-kit/media-kit-android-helper](https://github.com/media-kit/media-kit-android-helper).
- [media-kit](https://github.com/media-kit/media-kit), the Flutter player these builds are made for.

## Licences

- **This repository** (the workflows, scripts, tests and recipe files): MIT, `LICENSE`. The files made from the macOS
  recipe keep its MIT notice. The two Windows CMake files are made from shinchiro's recipe, which publishes no licence,
  so the MIT licence covers the changes made here only. `LICENSE` lists them.
- **The archives**: libmpv with FFmpeg as built is under the GNU LGPL version 3 or later as a whole, on Android too,
  each library keeping its own licence (OpenSSL and Mbed TLS under Apache-2.0, for example). `NOTICES.md` lists every
  library, its licence and your rights; the licence texts are in `licenses/` and in each archive.

## Changes

See `CHANGELOG.md`.
