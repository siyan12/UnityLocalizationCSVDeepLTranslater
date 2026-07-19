# 贡献指南 / Contributing

感谢你帮助改进 Unity Localization CSV DeepL Translator。提交前请先搜索现有 Issue，并让每次改动保持小而明确。

Thank you for improving Unity Localization CSV DeepL Translator. Search existing issues first and keep each change focused.

## 开发环境 / Development setup

需要 Python 3.10+：

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install ".[dev]"
```

提交 PR 前运行：

```bash
python -m py_compile translator_core.py gui_app.py app_storage.py
python -m pytest -q
python scripts/check_secrets.py
```

## 项目规则 / Project rules

- 测试必须使用 fake 或 mock DeepL client，绝不进行真实或计费 API 请求。
- 不得提交 API Key、`config.ini`、用户 CSV、译文、`build/`、`dist/` 或 EXE。
- 保留 CSV 编码、列、顺序、占位符、标签和换行；输出必须原子写入。
- 文件和网络工作不得阻塞 Tkinter 主线程，widget 操作只能在主线程执行。
- 行为变化应增加回归测试，并同步 README 中英文内容和 `CHANGELOG.md`。

- Tests must use a fake or mocked DeepL client and must never make real or billable API calls.
- Never commit API keys, `config.ini`, user CSVs, translations, `build/`, `dist/`, or executables.
- Preserve CSV encoding, columns, order, placeholders, tags, and line breaks; commit outputs atomically.
- Keep file and network work off the Tkinter main thread; update widgets only on that thread.
- Add regression tests for behavior changes and update both README languages and `CHANGELOG.md`.

PR 请说明目的、范围、验证命令及数据完整性或隐私影响。提交信息使用简短的祈使句，并避免把无关改动混入同一提交。

In the PR, explain the goal, scope, verification commands, and any data-integrity or privacy impact. Use short imperative commit messages and keep unrelated changes separate.
