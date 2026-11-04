# Validation levels

## Linux checks

```sh
scripts/check-static-v2.sh
scripts/prepare-source-v2.sh
scripts/test-build-v2.sh
scripts/verify-packages-v2.sh
```

`check-static-v2.sh` runs shell parsing, config validation, Python tests and patch structure checks. If installed, ShellCheck/actionlint also run. Local fixture tests exercise strict patch status, dirty sources, version rejection, cache invalidation, update error/no-update/mismatch paths, release evidence gates, real archive creation/extraction and checksum corruption rejection. A minimal synthetic ARM64 ELF fixture tests packaging and `readelf` checks without executing Android instructions; **it is not a compiled Bun/OpenCode binary**.

The package verifier checks exact payload path sets, matching DEB/Pacman/ZIP bytes, metadata, mode bits, ARM64/ELF64/PIE, `/system/bin/linker64`, absence of common glibc dependencies and RPATH/RUNPATH, known build-path leaks, SHA256SUMS and config/output provenance. It does not resolve every transitive Android system library or prove runtime compatibility. Release gates additionally bind evidence to the run, repository revision and output hashes.

## Android device matrix

Minimum target API is 29. Test proposed devices separately; none is currently claimed as passed:

| System | API | Required emphasis | Current status |
|---|---:|---|---|
| Android 11 | 30 | startup, seccomp and renderer | NOT TESTED |
| Android 12 | 31/32 | baseline behavior | NOT TESTED |
| Android 14 | 34 | TUI, PTY, background jobs | NOT TESTED |
| Android 15 | 35 | startup and interactive behavior | NOT TESTED |

API 29 is a compilation minimum, not evidence that Android 10 has been tested. Do not report a newer/older device result as covering all versions.

After package installation, run `bash scripts/test-runtime-v2.sh`. It collects Android model/API, version/help output, timeout and exit codes; missing Android or unsupported API fails. Run in a fresh output directory per test. These smoke results do not mark TUI passed.

Manually record an interactive session (install Termux `util-linux` if `script` is missing):

```sh
script -q -e -c 'opencode2' tui-session.log
printf 'terminal restore test\n'
stty -a
```

Inspect the actual application exit code and its visible interaction; a living `script`/PTY parent is not success. With a configured provider and a disposable project, verify all of the following:

1. version/help report expected application version and no native load errors;
2. TUI fully renders and accepts typed input;
3. open the project and read/write a disposable file;
4. launch and complete a subprocess;
5. launch a long-running command and background it;
6. use Ctrl+B while rendering and re-enter the background task (Issue #46);
7. switch Plan mode with Tab and verify the mode and subsequent behavior change (Issue #47);
8. ensure the intended private `libopentui.so` loads without platform detection errors (Issue #50);
9. exit normally and check echo, cursor, alternate screen and terminal input are restored.

Collect `tui-session.log`, smoke output, exact build-record/SHA256SUMS, command/reproduction sequence and any fatal signal output. Optional `adb logcat -b crash -d` may help; access varies by device. Review logs for tokens/project data before attaching them. Do not infer that seccomp is fixed merely from `--version` succeeding; exercise subprocess/background paths.

Copy `docs/device-results-v2.example.json` into a reviewed evidence file, bind it to the build run and all three output hashes, and mark only observed checks PASS. Keep failures and NOT TESTED values. A release requires all listed interactions to pass on at least one explicitly recorded supported device; stable promotion should require the maintainer's chosen full matrix. The pipeline never promotes to stable automatically.
