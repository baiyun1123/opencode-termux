# Hosted runner bootstrap (experimental)

The v2 workflow now installs Ubuntu build prerequisites and downloads the exact host Bun 1.4.2, Zig 0.16.0, Android NDK 28.2.13676358 (r28c), and LLVM 21.1.8 before preflight. `config/toolchains-v2.json` is the host download lock; its versions must agree with `versions-v2.json`. Archives come from the projects' official distribution hosts. All four archives use fixed SHA256 hashes. NDK's SHA256 was computed from the official archive after independently checking Google's published SHA1 from the official NDK wiki; both values and their provenance are retained in the lock. Downloaded archives are checked again after a cache restore; an invalid hash is never extracted or executed.

On GitHub-hosted Ubuntu, Rust/rustup is supplied by the runner image. Bun's checked-in Rust toolchain selects the compiler. On another clean Ubuntu host, install rustup from its official source before running the OS setup script. This setup does not install toolchains on persistent self-hosted runners; provision those deliberately using the same scripts.

```sh
scripts/setup-host-v2.sh
python3 scripts/bootstrap-v2.py
source build-v2/toolchain-env.sh
scripts/preflight-v2.sh
V2_JOBS=2 scripts/test-build-v2.sh
```

The bootstrap supports `--only bun zig` for a small host tool smoke test and `--validate` for offline lock validation. Installation lives inside the build work directory. LLVM's compiler resource directory is private and writable, so NDK runtime linking does not overwrite system compiler files. If a destination exists without the expected installation stamp, setup stops rather than deleting it.

## Resource profiles

`V2_RESOURCE_GATE=1` selects one of:

| `V2_RESOURCE_PROFILE` | RAM gate | free disk gate | Meaning |
|---|---:|---:|---|
| `dedicated` (default) | 30,000,000 KiB | 125,829,120 KiB | Original conservative dedicated-runner gate |
| `hosted-experimental` | 12,000,000 KiB | 41,943,040 KiB | Explicit experimental attempt with two build jobs |

These gates are operational settings, not measured proof of successful compilation. Hosted builds can still exhaust memory or disk. No swap changes or deletion of preinstalled system software are performed. Preflight reports all missing/mismatched tools at once and writes the actual memory/disk inventory to the Actions logs. `V2_JOBS` controls both Zig and Ninja parallelism.

Only the dedicated development branch in `baiyun1123/opencode-termux` starts a full hosted build on push. PR checks remain hosted and read-only; fork PRs do not execute on self-hosted runners. Manual dispatch continues to support dedicated runners. Neither push nor manual build publishes a release.

OpenTUI builds before the large patched Bun runtime. Successful native outputs are uploaded as diagnostic artifacts even if a later stage fails; these are not installable release packages. Verified package artifacts are uploaded only when the entire build and package checks succeed. Setup, download, preflight and compiler logs are retained on failure. Both host-tool downloads and output caches have exact keys, with no prefix fallback.

## First real CI observations

The first attempt passed the 20 regression tests but failed ShellCheck. Three issues were fixed (masked command statuses and a trap variable). The second attempt passed static checks including ShellCheck and reached build preflight, where `bun` was missing. Its runner reported about 15GiB RAM and 86GiB free disk. The automatic bootstrap and hosted profile address those observed prerequisites; a successful complete build is still required to validate the integration. Android runtime remains NOT TESTED.

Push builds cancel an obsolete push build for the same branch; manual builds retain their existing concurrency behavior. The OpenTUI stage can also be run locally with only Zig and the NDK; its stage-specific preflight does not require the unrelated Bun/LLVM toolchain. Only its distribution library is stripped of debug sections; upstream build outputs and patches remain unchanged.

The first bootstrap trial exposed an HTTP/2 download error and a pipeline exit status masked by `tee`. Downloads now use HTTPS over HTTP/1.1 with bounded retries for transfer failures and delete failed partial files. All workflow shell steps explicitly use Bash with pipefail, so setup/preflight failures stop the job rather than appearing successful.

A real local ARM64 OpenTUI build produced a 5.8MB ELF linked against Android libc/libm/libdl. The first binary still contained absolute C `__FILE__` strings after debug stripping. A separate version-scoped prefix-map patch fixes this at compilation time; the original Android compatibility patch remains unchanged. ELF verification now rejects known build-root paths before expensive downstream stages.

CI exposes source preparation, OpenTUI compilation, patched Bun compilation and CLI/packaging as separate steps. Verified OpenTUI and Bun outputs are cached immediately after their own successful verification, so a later stage failure does not discard earlier expensive work. Each stage has its own log file.

The first complete trial compiled the patched Android Bun and OpenCode CLI and created DEB/Pacman/ZIP files, then correctly rejected the CLI binary for a build-path leak. Its retained Bun artifact identified the leaked string as `build/android-release/codegen/cpp.rs`. The Android Bun profile does not enable the upstream `ci` config flag, so upstream C/C++ and Rust path remapping was disabled. A separate version-scoped build-script patch enables only path remapping for the Android ABI, without changing CI optimization settings or the SIGSYS implementation. Ninja generation must contain both C/C++ and Rust remapping flags, and output ELF scans remain mandatory.

The host Bun installation also creates the standard `bunx` symlink, which upstream declaration-generation scripts expect. Both commands were checked locally and report version 1.4.2.
