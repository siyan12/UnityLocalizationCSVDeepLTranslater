## Summary / 摘要

## Why / 原因

## Changes / 变更

## Test plan / 验证

- [ ] `python -m py_compile translator_core.py gui_app.py app_storage.py`
- [ ] `python -m pytest -q`
- [ ] `python scripts/check_secrets.py`
- [ ] Tests make no real or billable API requests.
- [ ] No API key, credential, user CSV, translation output, build, or executable is included.
- [ ] Core behavior changes include focused regression tests.
- [ ] CSV structure, placeholders, tags, line breaks, and atomic output remain protected.
- [ ] README Chinese/English sections and `CHANGELOG.md` are updated when behavior changes.
