#!/usr/bin/env bash
set -euo pipefail
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export REPO_ROOT
export V2_CONFIG="${V2_CONFIG:-$REPO_ROOT/config/versions-v2.json}"
# Read validated JSON; fixed keys and shell-quoted values only.
_v2_env="$(python3 "$REPO_ROOT/scripts/v2.py" env)"
eval "$_v2_env"
unset _v2_env
export WORK_DIR="${WORK_DIR:-$REPO_ROOT/build-v2}"
export DIST_DIR="${DIST_DIR:-$WORK_DIR/dist}"
export PACKAGE_DIR="${PACKAGE_DIR:-$WORK_DIR/packages}"
export BUN_SRC="${BUN_SRC:-$WORK_DIR/sources/bun}"
export OPENTUI_SRC="${OPENTUI_SRC:-$WORK_DIR/sources/opentui}"
export OPENCODE_WORKTREE="${OPENCODE_WORKTREE:-$WORK_DIR/sources/opencode}"
export ANDROID_NDK_HOME="${ANDROID_NDK_HOME:-${ANDROID_SDK_ROOT:-${ANDROID_HOME:-$HOME/Android/Sdk}}/ndk/$NDK_VERSION}"
export HOST_BUN="${HOST_BUN:-bun}"
export ZIG_BIN="${ZIG_BIN:-zig}"
export NDK_TOOLCHAIN="$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64"
export NDK_SYSROOT="$NDK_TOOLCHAIN/sysroot"
export BIONIC_SYSROOT_INC="$WORK_DIR/bionic-include"
export ZIG_LIBC="$WORK_DIR/bionic-libc.txt"
export OPENTUI_LIB="${OPENTUI_LIB:-$WORK_DIR/libopentui.so}"
export SOURCE_DATE_EPOCH="${SOURCE_DATE_EPOCH:-$(git -C "$REPO_ROOT" log -1 --format=%ct)}"
