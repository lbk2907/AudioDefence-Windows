#!/bin/bash
# Build OpenAL Soft for macOS: vendor/openal-mac/libopenal.dylib.
#
# The Windows build carries soft_oal.dll, committed in vendor/openal; the Mac build carries the same OpenAL
# Soft, built for the Mac, as libopenal.dylib in vendor/openal-mac.  It is committed too, so this is only
# needed to rebuild it - for another version, or for an Intel Mac - and the result is committed in its place.
# The game's HRTF needs nothing from here: assets/hrtf is committed, and tools/build_hrtf.py makes it.
#
# Usage:
#     tools/build_openal_mac.sh [--source DIR] [--arch arm64|x86_64]
#
#   --source DIR   an OpenAL Soft source tree to build.  Default: fetch the 1.25.2 release, the version of
#                  the Windows DLL, into vendor/build-openal/.
#   --arch ARCH    the architecture to build for.  Default: this machine's.
#
# Requires cmake and a C++ toolchain (the Xcode command line tools).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VERSION=1.25.2
SOURCE="${ROOT}/vendor/build-openal/openal-soft"
BUILD="${ROOT}/vendor/build-openal/build-mac"
ARCH="$(uname -m)"
if [[ "${1:-}" == "--source" ]]; then SOURCE="$2"; shift 2; fi
if [[ "${1:-}" == "--arch" ]]; then ARCH="$2"; shift 2; fi

if [[ ! -f "${SOURCE}/CMakeLists.txt" ]]; then
  echo "Fetching OpenAL Soft ${VERSION} into vendor/build-openal/..."
  mkdir -p "$(dirname "${SOURCE}")"
  curl -fL "https://github.com/kcat/openal-soft/archive/refs/tags/${VERSION}.tar.gz" \
    | tar xz -C "$(dirname "${SOURCE}")"
  mv "$(dirname "${SOURCE}")/openal-soft-${VERSION}" "${SOURCE}"
fi

echo "Configuring (${ARCH}) ..."
cmake -S "${SOURCE}" -B "${BUILD}" \
  -DCMAKE_BUILD_TYPE=Release \
  -DBUILD_SHARED_LIBS=ON \
  -DALSOFT_UTILS=OFF \
  -DALSOFT_EXAMPLES=OFF \
  -DALSOFT_TESTS=OFF \
  -DALSOFT_DLOPEN=ON \
  -DCMAKE_OSX_ARCHITECTURES="${ARCH}"

cmake --build "${BUILD}" --config Release

mkdir -p "${ROOT}/vendor/openal-mac"
install -m 755 "${BUILD}/libopenal.dylib" "${ROOT}/vendor/openal-mac/libopenal.dylib"

echo
echo "Built for ${ARCH}:"
ls -l "${ROOT}/vendor/openal-mac/libopenal.dylib"
echo "Commit it so a fresh clone builds without a toolchain."
