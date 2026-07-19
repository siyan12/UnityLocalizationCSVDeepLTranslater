# 发布检查清单 / Release Checklist

在公开 Release 前完成并记录本清单。第 1、2 节应在创建 tag 前完成；工作流创建草稿后，核对第 3 节，再批准受保护的 `publish` job。真实翻译会使用 DeepL 额度，因此必须由发布者明确决定执行；只使用仓库公开示例或完全虚构的非敏感文本。

Complete and record this checklist before making a Release public. Finish sections 1 and 2 before creating the tag; after the workflow creates its draft, verify section 3 and then approve the protected `publish` job. A real translation consumes DeepL quota, so the releaser must explicitly choose to run it. Use only the public sample or invented, non-sensitive text.

## 1. 版本与自动检查 / Version and automated checks

- [ ] `app_version.py`、`CHANGELOG.md` 和计划发布的 `vX.Y.Z` 一致。
- [ ] 当前提交已合并到 `main`，工作区干净。
- [ ] 在全新 Python 3.13.7 虚拟环境运行 `python -m pip install --require-hashes -r requirements-release.lock`。
- [ ] `python -m py_compile translator_core.py gui_app.py app_storage.py app_version.py`
- [ ] `python -m pytest -q`
- [ ] `python scripts/offline_release_smoke.py`
- [ ] `python scripts/check_secrets.py`
- [ ] `python scripts/verify_release_version.py --tag vX.Y.Z`
- [ ] `python -m PyInstaller --clean --noconfirm CSVTranslator.spec`
- [ ] `dist\CSVTranslator-X.Y.Z.exe --check-runtime`

发布 CI 使用 `requirements-release.lock`、Python 3.13.7 和固定提交的 Actions。修改依赖时，使用锁文件头部的命令重新生成并提交锁文件。

Release CI uses `requirements-release.lock`, Python 3.13.7, and Actions pinned to exact commits. When dependencies change, regenerate and commit the lock file using the command in its header.

## 2. 人工 CSV 往返 / Manual CSV round trip

- [ ] 将 `examples/offline_roundtrip_input.csv` 复制到界面显示的 `input` 目录；不得使用用户或项目机密文本。
- [ ] 启动待发布 EXE，确认标题版本、输入/输出路径、用量预估和取消按钮正确。
- [ ] 使用发布者自己的 DeepL Key 完成一次明确授权的翻译，确认没有源文、译文或 Key 出现在日志中。
- [ ] 确认输出未覆盖已有德语译文，URL-only 行保持空白，占位符、富文本标签和多行字段保持完整。
- [ ] 将输出导入受支持的 Unity Localization 1.4 CSV 工作流，确认 Key、Id、表头、列顺序、行顺序和 BOM 可接受。
- [ ] 删除本地 Key、输入和输出测试文件；不要把它们加入 Git。

- [ ] Copy `examples/offline_roundtrip_input.csv` to the UI-displayed `input` directory; never use user or project-confidential text.
- [ ] Start the release EXE and verify the title version, paths, estimate prompt, and cancellation control.
- [ ] With the releaser's own DeepL Key, explicitly authorize one translation and confirm logs contain no source text, translated text, or Key.
- [ ] Verify existing German text is preserved, the URL-only row remains empty, and placeholders, rich-text tags, and multiline fields survive.
- [ ] Import the output through the supported Unity Localization 1.4 CSV workflow and verify Key, Id, headers, column/row order, and BOM handling.
- [ ] Remove the local Key and test input/output files; never add them to Git.

## 3. GitHub 发布保护 / GitHub release protection

- [ ] `release` Environment 已启用必需审批人；分别审批签名/草稿 job 和最终公开 job。
- [ ] 可选签名 secrets 同时配置或同时留空：`WINDOWS_CERTIFICATE_BASE64`、`WINDOWS_CERTIFICATE_PASSWORD`。
- [ ] 仓库 ruleset 限制 `v*` tag 的创建/更新权限。
- [ ] 草稿 Release 中同时存在版本化 EXE 和同名 `.sha256`，签名状态与 Release 说明一致。
- [ ] 本地计算的 SHA-256 与发布的校验文件一致后再公开。

- [ ] The `release` Environment requires reviewers; separately approve the signing/draft job and the final publish job.
- [ ] Optional signing secrets are both configured or both absent: `WINDOWS_CERTIFICATE_BASE64`, `WINDOWS_CERTIFICATE_PASSWORD`.
- [ ] A repository ruleset restricts creation and updates of `v*` tags.
- [ ] The draft contains both the versioned EXE and matching `.sha256`, and its signing claim is accurate.
- [ ] A locally calculated SHA-256 matches the published checksum before publication.

## 4. 验收记录 / Sign-off record

- Commit SHA / 提交：
- Tag / 标签：
- EXE SHA-256：
- Unity / Localization package version：
- Tester / 验收人：
- Date / 日期：
- Notes / 备注：
