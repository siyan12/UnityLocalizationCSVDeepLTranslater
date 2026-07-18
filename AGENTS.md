# AGENTS.md

## Project

This repository is a small Python/Tkinter desktop tool that translates Unity Localization CSV files through DeepL. It is an external companion application, not a Unity project or Unity Package. Keep it lightweight; localization data integrity and clear failure reporting take priority over throughput.

Core files:

- `gui_app.py`: UI, configuration, background work, and status reporting.
- `translator_core.py`: CSV handling, language detection, placeholders, and DeepL calls.
- `README.md`: Chinese and English user documentation.
- `IMPROVEMENT_PLAN.md`: detailed roadmap, test matrix, and release work.

## Verification

- Target Python 3.10+ unless project metadata says otherwise.
- Syntax check: `py -3 -m py_compile translator_core.py gui_app.py`.
- Tests, once present: `py -3 -m pytest`.
- Tests must use a fake or mocked DeepL client and must never make real or billable API requests.
- Add focused tests for changed core behavior and regression tests for bug fixes when practical.

## Security and Privacy

- Never commit or expose API keys, credentials, `config.ini`, user CSV files, translated output, or sensitive localization text.
- Do not include complete keys or confidential text in logs, exceptions, tests, screenshots, or documentation.
- Store configuration in an explicit user-data location; prefer system credential storage over plaintext secrets.
- Do not add telemetry or send user data anywhere except the translation provider explicitly selected by the user.
- If exposure is suspected, identify affected paths without printing the secret and recommend revoking and rotating it.

## Data Integrity

- Preserve CSV encoding, headers, columns, row order, keys, IDs, quoting, commas, and multiline fields.
- Validate schemas before translation; report missing, empty, duplicate, extra, or unsupported fields with actionable file-level errors.
- Never modify source CSV files in place or silently discard data.
- Write outputs atomically through a temporary file and replacement.
- Preserve Unity Smart Strings, ICU expressions, printf/.NET placeholders, escaped braces, rich-text tags, and line breaks.
- Verify placeholder/tag structure after translation. Reject a changed cell rather than writing structurally corrupted text.
- Preserve existing translations by default; overwrite must be explicit.
- Clearly distinguish successful, partial, and failed results.

## Implementation

- Keep file/network work off the Tkinter main thread and perform widget operations only on it, using the queue/`after` pattern.
- Resolve application paths deliberately; do not depend on an unpredictable current working directory.
- Retry only transient provider/network failures. Do not retry authentication, invalid-parameter, or exhausted-quota errors.
- Keep provider-specific code separate from CSV and UI logic where practical.
- Keep user-facing behavior and both README language sections consistent.
- Do not commit generated builds, caches, local configuration, input, or output files. Publish packaged executables as release artifacts.
- Keep changes focused, preserve existing user work, and run relevant checks before handoff.
