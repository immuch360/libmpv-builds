#!/usr/bin/env bash
# Rebuild the four default-<abi>.jar of media-kit/libmpv-android-video-build v1.1.7 from the source archive of a
# libmpv-android-* release of this repository, with the steps of the recipe's buildscripts/bundle_default.sh and of
# its CI (.github/workflows/build.yaml at that tag).
#
#   android/build.sh <tag>-sources.tar.xz <work dir>
#
# The host is the one media-kit's CI used: Ubuntu 22.04 x86_64 with JDK 17, sudo (the recipe's scripts call it),
# autoconf, automake, libtool, pkg-config, meson, ninja, nasm, python3, git, wget, zip, unzip, binutils, and an
# Android SDK in ANDROID_HOME with its command line tools. The recipe installs NDK 25.2.9519653 (it compiles libmpv
# with it) and strips libmpv.so with the llvm-strip of NDK 27.3.13750724, which must be there too (the runner image
# had both).
# The rebuild is not bit for bit: the zip times and the build paths in FFmpeg's configuration string differ. What
# must match is printed at the end: FFmpeg's licence and configuration, mpv's configuration and the versions.
set -euo pipefail

[ $# -eq 2 ] || { sed -n '2,6p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' >&2; exit 2; }
sources="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")"
work="$2"

: "${ANDROID_HOME:?ANDROID_HOME must name an Android SDK}"
for tool in java javac sudo autoconf libtool pkg-config meson ninja nasm python3 git zip unzip tar xz wget strings; do
  command -v "$tool" >/dev/null || { echo "missing: $tool" >&2; exit 1; }
done
strip_ndk="$ANDROID_HOME/ndk/27.3.13750724"
[ -d "$strip_ndk" ] || { echo "missing: $strip_ndk (the recipe strips with its llvm-strip)" >&2; exit 1; }

# The recipe's folder layout, at the path of media-kit's CI under the work dir
mkdir -p "$work"
root="$(cd "$work" && pwd)/libmpv-android-video-build"
rm -rf "$root" "$work/unpacked"
mkdir -p "$work/unpacked"
tar -C "$work/unpacked" -xf "$sources"
top="$(find "$work/unpacked" -mindepth 1 -maxdepth 1 -type d -name 'libmpv-android-*-sources' | head -n 1)"
[ -n "$top" ] || { echo "$sources holds no libmpv-android-*-sources folder" >&2; exit 1; }
mv "$top/recipe" "$root"
bs="$root/buildscripts"
mkdir -p "$bs/deps"

# Each library as a git checkout of its own: the recipe's patch.sh runs git reset --hard and git apply in deps/<name>
for dep in "$top"/deps/*; do
  name="$(basename "$dep")"
  mv "$dep" "$bs/deps/$name"
  git -C "$bs/deps/$name" init -q
  git -C "$bs/deps/$name" add -A
  git -C "$bs/deps/$name" -c user.name=rebuild -c user.email=rebuild@localhost commit -q -m "$name as archived"
done

cd "$bs"
# The CI step "Symlink SDK"
mkdir -p sdk
ln -sfn "$ANDROID_HOME" sdk/android-sdk-linux

# bundle_default.sh, without its download of the libraries (they are the archived ones): the SDK packages and
# gas-preprocessor, the patches, the default FFmpeg options, the build of every architecture, the strip
TRAVIS=1 ./include/download-sdk.sh
./patch.sh
cp flavors/default.sh scripts/ffmpeg.sh
./build.sh
zip -qr debug-symbols-default.zip prefix/*/lib
for abi in arm64-v8a armeabi-v7a x86 x86_64; do
  "$strip_ndk/toolchains/llvm/prebuilt/linux-x86_64/bin/llvm-strip" --strip-all "prefix/$abi/usr/local/lib/libmpv.so"
done

# The helper library (media-kit-android-helper) and the four jars, as bundle_default.sh makes them
cd deps/media-kit-android-helper
chmod +x gradlew
./gradlew assembleRelease
out=app/build/outputs/apk/release
unzip -oq "$out/app-release.apk" -d "$out"
for abi in arm64-v8a armeabi-v7a x86 x86_64; do
  cp "$bs/prefix/$abi/usr/local/lib/libmpv.so" "$out/lib/$abi/"
done
cd "$out"
for abi in arm64-v8a armeabi-v7a x86 x86_64; do
  rm -f "default-$abi.jar"
  zip -qr "default-$abi.jar" "lib/$abi/"*.so
  mv "default-$abi.jar" "$work/"
done
mv "$bs/debug-symbols-default.zip" "$work/"

# What must match the release's own files
for abi in arm64-v8a armeabi-v7a x86 x86_64; do
  so="$bs/prefix/$abi/usr/local/lib/libmpv.so"
  echo "== $abi"
  strings "$so" | grep -E '^lib[a-z]+ license: ' | sort -u
  strings "$so" | grep -oE 'FFmpeg version n[0-9.]+' | head -n 1
  strings "$so" | grep -oE 'mpv v0\.[0-9]+\.[0-9]+-[0-9]+-g[0-9a-f]+' | head -n 1
  strings "$so" | grep -E '^-Dgpl=false ' | head -n 1
  strings "$so" | grep -cE -- '--disable-gpl --disable-nonfree --enable-version3' || true
done
sha256sum "$work"/default-*.jar "$work/debug-symbols-default.zip"
