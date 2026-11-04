# Update and pre-release operations

The new workflows do not publish on tags or on PRs, and never automatically promote stable releases.

## A: Candidate detection

`check-updates-v2.yml` runs at 03:27 UTC daily (11:27 Asia/Shanghai) and supports manual invocation. It queries official OpenCode stable releases, the fork's Android branch, Bun/OpenTUI stable releases and actual dependency manifests on the candidate Android SHA. The JSON report includes source SHAs, dependency compatibility, errors and untested patch/runtime status.

Only `config/update-candidates-v2.json` is proposed, through one persistent draft branch/PR (`automation/opencode2-update-candidates`). Identical candidates do not create daily commits or duplicate PRs; candidate fingerprints in the latest 100 PR bodies also suppress identical closed candidates even if the remote branch was removed. Missing permissions or API errors fail the job and produce a Summary/report artifact; they never report "no updates" as success. Enable the repository's Actions setting allowing PR creation if desired. The token has only contents/PR write permissions; no release step exists in this workflow.

The candidate PR is a review queue, not a production version change. A maintainer must review the fork delta, dependency versions and patch applicability before editing `versions-v2.json`. Newer official upstream code is not assumed to support Android. Do not automatically drop SIGSYS handling or apply guessed patches. Candidate dependency versions matching the lock proves only manifest compatibility, not ABI/runtime compatibility.

## B: Build and test

Update full commit SHAs and matching manifest metadata in a reviewed PR; keep application and package release versions separate. Re-run static checks, then manually dispatch `build-v2.yml` on the reviewed branch using the provisioned dedicated runner. Inspect logs and test all generated packages, with the exact downloaded artifacts on real Termux devices. The config's initial validation fields remain NOT TESTED until evidence warrants a reviewed change.

Full builds on every PR are deliberately not enabled until P0 has a successful complete build. PR checks run on hosted runners. Do not use `pull_request_target` or run external PR code on persistent self-hosted infrastructure. GitHub's own token-created PRs may not trigger other workflows automatically; dispatch validation after review when needed.

## C: Manual pre-release

Create GitHub environment `v2-release` with required reviewers and default-branch restrictions. These protection settings must be configured in GitHub; YAML alone does not enforce reviewer approval. Restrict who can manually run workflows and access the dedicated build runner.

1. Obtain a successful **manual** build run on the default branch using the exact production config; source override builds are test-only.
2. Commit and review a device report based on `device-results-v2.example.json` on the default branch. Copy run ID and all output hashes from that build's record. Record model, Android version/API, tester/date and logs; set approval to approved only after actual review.
3. Dispatch `release-v2.yml` on the default branch with `build_run_id` and the reviewed `device_report_path`.
4. The workflow verifies origin, workflow path, event, branch and success; downloads the exact named build artifact; checks packages against the build revision's config and provenance; validates device evidence; then publishes an `opencode2-v<package-version>` **pre-release**.

An existing release/tag is not overwritten. Use a new reviewed release version for another release. Release notes include source/dependency/toolchain config, explicitly tested devices, known limitations, install commands, checksums and build-commit file changes. No stable promotion automation is included.

Known unresolved compatibility work: actual Bun/LLVM integration, optional native dependencies with frozen installs, fork regex patch robustness as OpenTUI evolves, subprocess/PTY and Plan mode behavior, and full supported-device coverage. File watching stays disabled; fff is expected to use its JavaScript fallback. All of these require observation, not optimistic status changes.
