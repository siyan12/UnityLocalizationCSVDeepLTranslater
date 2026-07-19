# Changelog

本项目的重要变更记录在此。格式参考 [Keep a Changelog](https://keepachangelog.com/en/1.1.0/)，版本遵循 [Semantic Versioning](https://semver.org/spec/v2.0.0.html)。

All notable changes are documented here. This format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Operating-system credential storage for DeepL API keys.
- Strict CSV schema validation, atomic output, and placeholder/tag/line-break protection.
- Offline fake-client tests and Windows/Linux CI across supported Python versions.
- Batched DeepL requests, task-local cross-file caching, usage estimates, and cooperative cancellation.
- Contributor, security, issue, and pull-request guidance.

### Changed

- User data now uses explicit per-user application directories.
- Provider failures are classified into safe, actionable categories.
- Documentation now distinguishes tested compatibility, source platforms, and prebuilt platforms.

### Security

- Credential scanning rejects tracked plaintext configuration and likely API keys.
- Logs and failure reports avoid source text, translated text, and credentials.

## [1.0.0] - 2025-10-07

### Added

- Initial public release.

[Unreleased]: https://github.com/siyan12/UnityLocalizationCSVDeepLTranslater/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/siyan12/UnityLocalizationCSVDeepLTranslater/releases/tag/v1.0.0
