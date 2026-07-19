# 安全政策 / Security Policy

## 支持范围 / Supported versions

安全修复以 `main` 和最新 GitHub Release 为目标；旧版本不保证继续获得安全更新。

Security fixes target `main` and the latest GitHub Release. Older versions are not guaranteed to receive security updates.

## 私密报告 / Private reporting

不要在公开 Issue 中披露漏洞细节、API Key、凭据或机密本地化文本。请使用仓库的 [GitHub 私密漏洞报告](https://github.com/siyan12/UnityLocalizationCSVDeepLTranslater/security/advisories/new)，提供受影响版本、脱敏复现步骤、影响和建议修复。不要附上真实密钥或用户 CSV。

Do not disclose vulnerability details, API keys, credentials, or confidential localization text in a public issue. Use [GitHub private vulnerability reporting](https://github.com/siyan12/UnityLocalizationCSVDeepLTranslater/security/advisories/new) and include the affected version, sanitized reproduction steps, impact, and a suggested fix. Never attach a real key or user CSV.

如果该私密报告入口不可用，请只创建一个不含漏洞细节的公开 Issue，请求维护者启用私密报告；在私密渠道可用前不要发布技术细节。

If the private reporting form is unavailable, open a public issue containing no vulnerability details and ask the maintainer to enable private reporting. Do not publish technical details until a private channel is available.

若 DeepL API Key 可能泄露，请立即在 DeepL 账户中撤销并轮换；删除仓库内容或关闭 Issue 不能使已暴露的密钥重新安全。

If a DeepL API key may have been exposed, revoke and rotate it immediately. Deleting repository content or closing an issue does not make an exposed key safe again.
