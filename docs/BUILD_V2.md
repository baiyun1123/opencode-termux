# OpenCode 2 Android build

This pipeline is implemented but the complete Bun/LLVM/CLI build has **NOT BEEN TESTED** in the implementation environment. P0 patch-target checks and local infrastructure tests pass; this does not establish that P0's full build acceptance has passed. P1–P3 are available for evaluation, not validated releases. No Android system version is declared runtime-compatible by this change.

## Source audit and isolation

The implementation is based on `guysoft/opencode-termux` commit `20fe9d28c473e329722a63610ac0254652a8382a`, on the independent branch `feat/opencode2-android-auto-build`. The initial file snapshot was verified against Git blob hashes while a slow clone completed; the final branch uses the real upstream history. Apply the supplied patch to a normal upstream checkout; it does not touch PR #24 or the v1 workflow/scripts.

The Android fork is locked to `6b03c82fc8e18f6119ae8a698e461b1219242715`. Its `packages/cli/script/build.ts` explicitly registers `{ os: "linux", arch: "arm64", abi: "android" }`, accepts `OPENCODE_BUN_RUNTIME`, stubs Parcel watching, and rewrites OpenTUI native asset resolution to accept Android and `OPENTUI_LIB_PATH`. These changes are already in the fork; no duplicate local application patch is added. The original upstream default branch is not substituted.

The fork's root manifest pins `bun@1.4.2`; its catalog pins `@opentui/core` and `@opentui/solid` to `0.5.10`. CLI source metadata says `1.18.4`, whereas the application banner is intentionally `2.0.0-android-termux.2`. The package release `1.0.3` is independent. Bun `bun-v1.4.2` resolves to `744846f844374847c902b5e7fd59b4342a51ef99`. OpenTUI's annotated `v0.5.10` tag resolves through tag object `07baf92f6cae4bc5596d2af9c6651cd0864ee12e` to commit `f6673a04ccb671b9207da358c57152bfd27c781f`.

Both existing Android patches remain byte-for-byte unchanged. The Bun patch provides seccomp SIGSYS to ENOSYS fallback, signal forwarding and subprocess signal-mask handling. The OpenTUI patch provides bionic headers/linking, clipboard handling and coordinate bounds checks for the background-command crash. Both patches apply and reverse-check against all affected files fetched at the locked commits. This verifies patch applicability only; neither C++ nor Zig has been compiled here. Whether these fixes exist in newer upstream versions is not established; updates require review.

## Ubuntu prerequisites

Use an isolated Ubuntu 24.04 x86_64 machine. Conservative starting capacity: 32GB RAM, 120GiB free SSD, 6-hour CI timeout; these are proposed resource gates, not measured successful build requirements. Standard hosted runners often cannot meet the gates. The workflow records memory/disk and stops before compiling when inadequate. Select a dedicated runner labeled `self-hosted,linux,x64,opencode-v2`. Never expose it to untrusted fork code.

Install Git, Python 3, build-essential, Ninja, CMake, pkg-config, zip/unzip, xz-utils, binutils, dpkg-dev, Ruby, Perl, autoconf, automake, libtool, Rust/rustup and LLVM/Clang/lld **21** using your distro/trusted toolchain repositories. Install native Linux Bun **1.4.2**, Zig **0.16.0**, and Android NDK **28.2.13676358** (SDK manager package `ndk;28.2.13676358`). Bun's checked-in Rust toolchain controls its nightly; make the Android Rust target available using that toolchain. The Bun build may download pinned build dependencies; this is not an offline build.

Example after provisioning (no maintainer-specific path required):

```sh
export ANDROID_NDK_HOME="$ANDROID_HOME/ndk/28.2.13676358"
export HOST_BUN="$(command -v bun)"
export ZIG_BIN="$(command -v zig)"
export BUN_TOOLCHAIN_LLVM=/usr/lib/llvm-21
export WORK_DIR="$PWD/build-v2"
scripts/preflight-v2.sh
scripts/prepare-source-v2.sh
scripts/test-build-v2.sh
```

`WORK_DIR` must be an absolute path. `BUN_TOOLCHAIN_LLVM` must contain `bin/clang` and `bin/ld.lld` version 21. The legacy fallback assembled symlinks and then wrote wrappers over them, risking writes into the system toolchain. It is removed. If Bun requires a writable Clang resource directory, provision a **private copy** of LLVM with NDK compiler-rt libraries, then point `BUN_TOOLCHAIN_LLVM` at it. This integration still needs validation on the build host; do not modify `/usr/lib` through symlinks.

`config/versions-v2.json` is the only production version source. Environment version overrides are intentionally ignored. `V2_CONFIG` can point to a separate reviewed config for experiments. Paths can be overridden with `WORK_DIR`, `DIST_DIR`, `PACKAGE_DIR`, `BUN_SRC`, `OPENTUI_SRC`, `OPENCODE_WORKTREE`, `OPENTUI_LIB`; all are local paths. Use a new work directory after changing source locks.

## Reproducibility and patches

OpenTUI's versioned Zig dependency archive is extracted using its checked-in preparation script, so a clean checkout provides Yoga before the sysroot shims are copied. Bun's build config explicitly sets Android API 29 (its upstream default is 28), using its supported JSON configure route followed by Ninja.

Source preparation fetches only a full locked commit, checks out detached HEAD, verifies origin and final SHA, applies a patch or identifies an already applied patch, and rejects incompatible/partial patches. Existing checkouts at another SHA are rejected without cleaning or resetting developer work. Expected patched file contents are verified with a temporary Git index. Application preparation additionally checks dependency versions, source metadata, lockfile and Android build capabilities.

Application dependencies use `bun install --frozen-lockfile --ignore-scripts --os='*' --cpu='*'`, and CLI build uses `--skip-install` so the build script cannot silently reinstall unlocked dependencies. The patched Android Bun is mandatory: there is no fallback to the unpatched release binary. Whether the fork needs additional cross-platform optional artifacts with skipped lifecycle scripts must be confirmed by the full build.

Caches contain only Bun and OpenTUI outputs and their hash manifests, keyed by the whole config, full source SHAs, NDK/Zig/API/architecture, patch bytes and build helper bytes. No prefix fallback keys are allowed. Local reuse checks hashes and the same key. Source trees and native build intermediates are not cached. Delete stale artifacts or use a fresh `WORK_DIR` when a cache check rejects them.

Source SHA/patch hash records are saved under `build-v2/logs`; `build-record.json` includes source/toolchain config, repository commit and output SHA256 values, without build-machine paths. Package timestamps, owner/group and compression settings are normalized using `SOURCE_DATE_EPOCH`. This establishes deterministic packaging for identical inputs; bit-for-bit reproducibility of upstream Bun/CLI compilation is **not yet established**.

## GitHub Actions

`Build OpenCode 2 Android` runs local static/regression checks for PRs on a hosted runner. Full builds are manual while P0 remains unverified. They require a provisioned toolchain, including on a hosted runner; the workflow does not silently download arbitrary toolchains. Select `self-hosted` once the dedicated runner is configured. `opencode_commit` optionally accepts a full source SHA for a test build; dependency/source checks remain mandatory and overridden config artifacts cannot be released against the production lock.

Full-build logs are uploaded even when a step fails. Only successful verified packages are uploaded as `opencode2-android-<run_id>`. The token has read-only repository permissions. No PR receives publishing credentials and fork PRs never execute on the self-hosted runner. Linux builds always report Android runtime as NOT TESTED.

## Installation after a successful real build

For standard Termux (Debian packages), download the DEB and checksums from the same build:

```sh
sha256sum -c SHA256SUMS
apt install ./opencode2_1.0.3_aarch64.deb
opencode2 --version
opencode2 --help
opencode2
```

For Termux with Pacman, `pacman -U opencode2-1.0.3-1-aarch64.pkg.tar.xz`. Pre-release hyphens are converted to underscores in Pacman's version; its final `-<revision>` remains the package revision. DEB and ZIP retain the release version.

ZIP manual installation (from the extracted directory):

```sh
mkdir -p "$PREFIX/libexec/opencode2"
install -m755 opencode2 "$PREFIX/bin/opencode2"
install -m755 opencode2.bin "$PREFIX/libexec/opencode2/opencode2.bin"
install -m644 libopentui.so "$PREFIX/libexec/opencode2/libopentui.so"
```

The wrapper resolves binary and renderer as one pair, exports `OPENTUI_LIB_PATH`, and disables unsupported file watching. It owns only `bin/opencode2` and `libexec/opencode2/*`; the v1 package's binary and `lib/libopentui.so` are untouched. These commands describe future verified artifacts; this change does not contain a newly compiled Android binary.
