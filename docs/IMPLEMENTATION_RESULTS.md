# 实施结果（2026-11-04）

已在独立分支 `feat/opencode2-android-auto-build` 实际开发；基线是 `guysoft/opencode-termux@20fe9d28c473e329722a63610ac0254652a8382a`。未改写 PR #24，也未修改 v1 的工作流和构建脚本。尚未向 GitHub 推送、创建 PR 或触发远程 Actions。

## 已实现

- 统一 JSON 版本锁，区分 CLI 源码元数据版本、应用显示版本、安装包发行版本；记录 Bun/OpenTUI/OpenCode 完整 SHA。
- 自动获取锁定源码，验证依赖、补丁和工作树；补丁已应用会明确输出，冲突或额外输入会失败，不清理开发者修改。
- 移除本机路径。保留 SIGSYS 和 OpenTUI 补丁原文。修复 LLVM 回退逻辑可能通过符号链接覆盖系统编译器的问题。
- 修复清洁 OpenTUI 检出遗漏 Zig 依赖解包的问题；显式给 Bun 配置 API 29，避免其默认 API 28 与配置不一致。
- 提供只读构建 CI、严格缓存、日志与产物上传；P0 全量编译未验证前，PR 自动运行静态检查，完整编译由维护者手动触发。
- 修复 DEB 路径多嵌套一层 data 的问题；统一二进制/动态库配对加载；保留 v1/v2 并存安装路径。
- 生成 DEB、Pacman、ZIP、SHA256SUMS 和构建记录；校验内容、权限、版本、ELF、依赖、路径泄漏及输出哈希。
- 每日检测更新，只生成候选升级 PR，具备重复候选识别、依赖比对和权限失败报告；不会自动更改生产锁或合并。
- 手动预发布流程验证构建来源、产物和真机证据；只发布 Pre-release，稳定版不自动发布。
- Termux 冒烟测试与详细的 TUI/PTY/Plan/Ctrl+B 真机回归清单。

## 实际验证

| 命令/检查 | 结果与边界 |
|---|---|
| `scripts/check-static-v2.sh` | 通过：Shell 语法、配置、20 项 Python 回归、补丁结构 |
| `scripts/prepare-source-v2.sh` | 通过：三个真实仓库锁定 SHA 检出，严格补丁与依赖检查；重复执行通过 |
| 真实 Bun/OpenTUI 补丁目标文件 apply/reverse/exact-tree 检查 | 通过；不等于 C++/Zig 编译通过 |
| `python3 scripts/check-updates-v2.py` | 真实 GitHub 查询成功，0 个错误；发现 3 个候选，生产配置未变 |
| 三种包创建、解包、重复打包哈希一致性、损坏拒绝 | 测试通过；使用明确标注的合成 ELF 测试夹具，非真实 OpenCode 构建产物 |
| 预发布 Pacman 版本与包装器配对选择 | 测试通过 |
| 发布真机证据拒绝逻辑与 PR 去重/权限异常 | 本地测试通过，未实际创建 PR/发布 |
| 三份新增 Actions YAML | 本地 YAML 解析通过；未在 GitHub 运行，未运行 actionlint |
| `python3 -m py_compile ...`、`git diff --check` | 通过 |
| `scripts/test-build-v2.sh` | 未通过环境预检：`Missing tool: cmake`，没有进入编译 |
| ShellCheck | 环境未安装，未执行；Shell 语法检查已执行 |

当次更新报告发现：OpenCode 正式版 `v1.19.5`、Bun `bun-v1.4.4`、OpenTUI `v0.8.2`；Android 分支 SHA 未变，其 Bun/OpenTUI 清单仍与当前锁匹配。此信息仅代表查询时的候选，未升级或验证这些新版本。

环境约 9.7GiB 内存、60GiB 可用磁盘；缺少 CMake、Ninja、Rust/rustup、Bun、Zig、LLVM 21 与配置所需 NDK。低于为完整编译设置的保守门槛（32GB RAM、120GiB 磁盘）；门槛并非实测成功构建的资源数据。

## 尚未验证

P0 的源码准备与严格补丁部分已通过，但完整 Bun/OpenTUI/CLI 编译尚未通过，因此不能声称 P0 完整验收。P1–P3 的代码已实现，本地基础设施测试通过，远程 Actions、真实安装包、真机运行、PR 创建和发布仍未验证。

Android 11、12、14、15 全部为 **NOT TESTED**。Issue #46 后台任务崩溃、#47 Plan 切换和 #50 动态库识别仍需真机回归；保留相应现有修复不代表这些问题已解决。冻结依赖安装下的可选原生组件和 OpenTUI 注入逻辑，也要通过全量构建与交互验证。不能把 `--version` 成功当作 TUI 通过。

## 使用入口

- 环境、源码、构建与 Termux 安装命令：[BUILD_V2.md](BUILD_V2.md)
- 静态和真机验证：[TESTING_V2.md](TESTING_V2.md)
- Actions 配置、每日候选 PR、维护升级与人工预发布：[RELEASE_V2.md](RELEASE_V2.md)
- 实际日志与来源记录：本目录的 `validation/`。

准备专用 Ubuntu Runner（`self-hosted,linux,x64,opencode-v2`）后，运行 `scripts/preflight-v2.sh` 和 `scripts/test-build-v2.sh`，或手动运行 `Build OpenCode 2 Android`。GitHub 中需要自行配置 `v2-release` 环境的 required reviewers；YAML 无法代替仓库保护设置。

真实构建成功后，Termux Debian 版安装示例：

```sh
sha256sum -c SHA256SUMS
apt install ./opencode2_1.0.3_aarch64.deb
opencode2 --version
opencode2 --help
opencode2
```

本交付只有源码、补丁、文档和验证记录，未提供冒充真实构建的 Android 二进制文件。

## 修改/新增文件

修改：

- `.gitignore`
- `scripts/build-bun-android.sh`
- `scripts/build-opencode2-android.sh`
- `scripts/build-opentui-v2.sh`
- `scripts/env-v2.sh`
- `scripts/make-packages-v2.sh`

新增：

- `.github/workflows/build-v2.yml`
- `.github/workflows/check-updates-v2.yml`
- `.github/workflows/release-v2.yml`
- `config/versions-v2.json`
- `docs/BUILD_V2.md`
- `docs/IMPLEMENTATION_RESULTS.md`
- `docs/RELEASE_V2.md`
- `docs/TESTING_V2.md`
- `docs/device-results-v2.example.json`
- `docs/validation/full-build-attempt.txt`
- `docs/validation/source-bun.json`
- `docs/validation/source-opencode.json`
- `docs/validation/source-opentui.json`
- `docs/validation/source-preparation.txt`
- `docs/validation/static-checks.txt`
- `docs/validation/update-check.json`
- `scripts/check-static-v2.sh`
- `scripts/check-updates-v2.py`
- `scripts/preflight-v2.sh`
- `scripts/prepare-source-v2.sh`
- `scripts/release-v2.py`
- `scripts/test-build-v2.sh`
- `scripts/test-runtime-v2.sh`
- `scripts/update-pr-v2.py`
- `scripts/v2.py`
- `scripts/verify-packages-v2.py`
- `scripts/verify-packages-v2.sh`
- `tests/test_v2.py`
