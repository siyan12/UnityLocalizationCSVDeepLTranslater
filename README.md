# CSV 批量翻译工具 (CSV Translator)

[English Version](#-english-version)

这是一个使用 Python 和 DeepL API 开发的桌面小工具，**专为翻译 Unity Localization 插件导出的 CSV 表格而设计**。它可以快速、批量地将指定列从源语言翻译成多种目标语言，极大简化多语言本地化流程。

Use deepL API to translate CSV table that outputed from Unity Localization.

![UI](docs/UIimage.png)

---

### 👋 首次发布说明

你好！我是**老白**，一名游戏开发者。这是我第一次公开发布个人项目，主要目的是为了方便自己和同样有需求的朋友。

项目中可能存在一些未被发现的 Bug 或疏漏之处，非常欢迎你通过 [Issues](https://github.com/siyan12/UnityLocalizationCSVDeepLTranslater/issues) 提出反馈和建议，帮助我把这个小工具做得更好！

-   **工作室**: LauNewBee
-   **我的作品**: [欢迎访问我的 Steam 开发者页面](https://store.steampowered.com/developer/LauNewBee)

---

## ✨ 功能特性

-   **专为 Unity 设计**：支持 Unity Localization 1.4 文档中的标准 CSV 与 CSV (With Comments) 表格结构。
-   **图形化界面**：简洁直观的图形界面，无需命令行操作。
-   **批量翻译**：一次性将 CSV 文件中的文本翻译成多种指定语言。
-   **安全配置**：DeepL API Key 保存到操作系统凭据库，不写入项目或 `config.ini`。
-   **平台支持**：提供 Windows `exe`；Python 3.10+ 源码可在支持 Tkinter 的平台运行。

---

## 🚀 快速开始 (普通用户)

1.  **下载与解压**
    -   前往本项目的 [Releases 页面](https://github.com/siyan12/UnityLocalizationCSVDeepLTranslater/releases)。
    -   下载最新的 `CSVTranslator-vX.X.X.zip` 压缩包并解压。

2.  **准备文件**
    -   首次启动后，界面会显示用户数据目录中的 `input` 和 `output` 完整路径。
    -   将从 Unity 导出的 `.csv` 文件放入该 `input` 文件夹。

3.  **运行与翻译**
    -   双击运行 `CSVTranslator.exe`。
    -   在程序界面的 **API Key 输入框**中填入 Key，然后点击 **Save API Key**；Key 会保存到操作系统凭据库。
    -   当前版本固定从 `English(en)` 翻译，并自动填充文件中检测到的受支持目标语言列；点击“开始翻译”。
    -   翻译完成后，结果会保存在界面显示的 `output` 文件夹中。

---

## 📂 数据保存位置

程序不会依赖启动时的当前目录。Windows 数据目录默认为
`%LOCALAPPDATA%\UnityLocalizationCSVDeepLTranslater`；macOS 默认为
`~/Library/Application Support/UnityLocalizationCSVDeepLTranslater`；Linux 默认为
`$XDG_DATA_HOME/UnityLocalizationCSVDeepLTranslater`（未设置时使用
`~/.local/share/UnityLocalizationCSVDeepLTranslater`）。该目录只放 `input` 和
`output` CSV；API Key 不保存在其中。

---

## ⚠️ 注意事项

-   **API Key**：Key 通过 Python `keyring` 保存到系统凭据库。请勿在日志、Issue、CSV 或配置文件中粘贴 Key。若怀疑泄露，请立即在 DeepL 账户中停用/删除该 Key 并创建新 Key；还可在系统的“凭据管理器/钥匙串”中删除服务名 `UnityLocalizationCSVDeepLTranslater` 的条目。
-   **旧版迁移**：新版本不会读取旧的 `CSVtranslator-run/config.ini`。请在新界面重新保存 Key，确认可用后安全删除旧文件；若旧文件曾被分享，必须轮换 Key。
-   **凭据库不可用**：程序会明确报错且不会退回明文保存。请确认已安装 `keyring`，并确保系统凭据服务可用。
-   **隐私**：待翻译的 CSV 文本会发送给 DeepL；程序不会额外上传这些文本，UI 日志也不会显示源文或译文内容。
-   **费用**：DeepL API 的免费额度有限，请注意使用量，避免产生不必要的费用。
-   **CSV 格式**：文件必须是带或不带 UTF-8 BOM 的 UTF-8 CSV，包含 `Key` 或 `Id` 标识列、固定源列 `English(en)`，以及至少一个受支持的目标语言列。每行必须有非空 `Key` 或正数 `Id`；新条目可在有 `Key` 时将 `Id` 留空或设为 `0`。空/重复表头、字段数量异常、重复的非空 Key/已分配 Id 和已知但不支持的标准语言列会在调用 DeepL 前以文件级错误拒绝；不会生成该文件的输出。
-   **支持的目标列**：`Chinese (Simplified)(zh)`、`Chinese (Traditional)(zh-Hant)`、`French(fr)`、`German(de)`、`Japanese(ja)`、`Korean(ko)`、`Polish(pl)`、`Portuguese(pt)`、`Russian(ru)`、`Spanish(es)`、`Turkish(tr)`。评论列与自定义元数据列会原样保留，不会送去翻译。
-   **往返保证**：保留输入是否含 UTF-8 BOM、表头和列顺序、逻辑行顺序，以及字段中的逗号、双引号和多行文本。输出采用标准 CSV 最小引号规则，因此不承诺与输入逐字节相同。
-   **安全输出**：每个 CSV 先写入输出目录中的专用临时文件，完成刷新并关闭后才原子替换最终文件。读取、翻译或写入失败不会覆盖上一次成功输出，正常中断也会清理临时文件。
-   **结果状态**：`success` 表示文件全部成功；`partial` 表示至少一个单元格成功、同时有失败单元格，失败格保留原值；`failed` 表示文件没有可提交的成功译文或发生文件级错误，因此不提交新输出。批次混合这些结果时，界面会明确显示部分完成。
-   **失败清单**：日志会列出失败单元格的文件名、CSV 行号、目标列、目标语言和安全错误信息，不包含源文、译文或 API Key，便于定位并重试。
-   **Unity 兼容范围**：自动测试以 Unity Localization 1.4 文档给出的 `Key,Id,Locale...` 与 CSV (With Comments) 结构为基准，并支持仅含 `Key` 或 `Id` 的合法变体。自定义列会保留；但自定义 Locale Field Name 无法自动识别为语言列，其他包版本也尚未做 Unity Editor 端到端验证。
-   **结构保护**：工具会保留 .NET/Python/printf 占位符、Unity Smart String、ICU、富文本标签与换行；如果译文结构不同，该单元格会保留原值并报告失败。当前嵌套 Smart String/ICU 会整段保护，因此表达式内部的分支文案不会翻译。

## 🧪 离线测试

安装开发依赖后运行 `python -m pytest`。测试使用 fake DeepL client，并由自动 fixture
禁止网络连接，不会调用真实或计费 API。

## 🔐 贡献时的凭据检查

仓库的 GitHub Actions 会拒绝被跟踪的 `config.ini` 和疑似凭据。贡献者也可安装
`pre-commit` 后运行 `pre-commit install` 启用同一项提交前检查，或手动运行
`python scripts/check_secrets.py`。检查只报告文件名和规则名，不输出疑似密钥。

## 📄 许可证

本项目使用 [MIT License](LICENSE)。

---
---

# 🇬🇧 English Version

This is a desktop tool developed with Python and the DeepL API, **specifically designed for translating CSV files exported from the Unity Localization package**. It can quickly batch-translate specific columns from a source language to multiple target languages, greatly simplifying the localization workflow.

Use deepL API to translate CSV table that outputed from Unity Localization.

![UI](docs/UIimage.png)

---

### 👋 First Release Note

Hi there! I'm **Lao Bai**, a game developer. This is the first personal project I've ever released publicly. My main goal was to create a handy tool for myself and other developers with similar needs.

There might be some undiscovered bugs or oversights. I would be very grateful if you could provide feedback and suggestions via the [Issues](https://github.com/siyan12/UnityLocalizationCSVDeepLTranslater/issues) page to help me improve it!

-   **Studio**: LauNewBee
-   **My Work**: [Check out my Steam Developer Page](https://store.steampowered.com/developer/LauNewBee)

---

## ✨ Features

-   **Designed for Unity**: Supports the standard CSV and CSV (With Comments) table layouts documented for Unity Localization 1.4.
-   **GUI**: Simple and intuitive graphical user interface, no command line needed.
-   **Batch Translation**: Translate text in a CSV file into multiple target languages at once.
-   **Secure Configuration**: The DeepL API Key is stored in the operating system credential store, never in the project or `config.ini`.
-   **Platform Support**: A Windows `exe` is provided; the Python 3.10+ source runs on platforms with Tkinter support.

---

## 🚀 Quick Start (For Users)

1.  **Download and Unzip**
    -   Go to the [Releases page](https://github.com/siyan12/UnityLocalizationCSVDeepLTranslater/releases) of this project.
    -   Download and unzip the latest `CSVTranslator-vX.X.X.zip` archive.

2.  **Prepare Files**
    -   After the first launch, the UI displays the full paths of the `input` and `output` folders in the user data directory.
    -   Place the `.csv` file exported from Unity into that `input` folder.

3.  **Run and Translate**
    -   Double-click `CSVTranslator.exe` to run it.
    -   Enter your DeepL API Key in the UI and click **Save API Key**. It is saved in the operating system credential store.
    -   This version always translates from `English(en)` and automatically fills the supported target-language columns detected in the file. Click "Start Translation."
    -   The translated file will be saved in the `output` folder shown in the UI.

---

## 📂 Data Locations

The application does not depend on its launch working directory. The default data
directory is `%LOCALAPPDATA%\UnityLocalizationCSVDeepLTranslater` on Windows,
`~/Library/Application Support/UnityLocalizationCSVDeepLTranslater` on macOS, and
`$XDG_DATA_HOME/UnityLocalizationCSVDeepLTranslater` on Linux (falling back to
`~/.local/share/UnityLocalizationCSVDeepLTranslater`). It contains only the `input`
and `output` CSV folders; the API Key is not stored there.

---

## ⚠️ Important Notes

-   **API Key**: The Key is stored through Python `keyring` in the system credential store. Never paste it into logs, issues, CSV files, or configuration files. If exposure is suspected, disable/delete it in your DeepL account immediately and create a replacement. You may also remove the entry named `UnityLocalizationCSVDeepLTranslater` from the OS Credential Manager/Keychain.
-   **Legacy migration**: New versions do not read the old `CSVtranslator-run/config.ini`. Save the Key again in the new UI, verify it, and then securely delete the old file. Rotate the Key if that file was ever shared.
-   **Unavailable credential store**: The application reports an error and never falls back to plaintext. Ensure `keyring` is installed and the OS credential service is available.
-   **Privacy**: CSV text selected for translation is sent to DeepL. The application does not upload it elsewhere, and the UI log does not display source or translated text.
-   **Costs**: The DeepL API has a limited free tier. Be mindful of your usage to avoid unexpected charges.
-   **CSV Format**: Files must be UTF-8 CSV, with or without a UTF-8 BOM, and contain a `Key` or `Id` identity column, the fixed `English(en)` source column, and at least one supported target-language column. Every row needs a non-empty `Key` or a positive `Id`; new entries may use an empty or zero `Id` when a `Key` is present. Empty or duplicate headers, inconsistent field counts, duplicate non-empty Keys/assigned Ids, and known unsupported standard language columns are rejected with a file-level error before DeepL is called; no output is produced for that file.
-   **Supported target columns**: `Chinese (Simplified)(zh)`, `Chinese (Traditional)(zh-Hant)`, `French(fr)`, `German(de)`, `Japanese(ja)`, `Korean(ko)`, `Polish(pl)`, `Portuguese(pt)`, `Russian(ru)`, `Spanish(es)`, and `Turkish(tr)`. Comment and custom metadata columns are preserved and are not sent for translation.
-   **Round-trip guarantees**: The tool preserves the input BOM state, header and column order, logical row order, and commas, double quotes, and multiline text inside fields. Output uses standard minimal CSV quoting, so byte-for-byte identity is not promised.
-   **Safe output**: Each CSV is written to a dedicated temporary file in the output directory, flushed, closed, and only then atomically replaces the destination. Read, translation, or write failures never overwrite the last successful output, and orderly interruption cleans up the temporary file.
-   **Result states**: `success` means the file completed without cell failures; `partial` means at least one cell succeeded while failed cells retained their original values; `failed` means there was no successful translation to commit or a file-level error occurred, so no new output is committed. Mixed batches are clearly shown as partially complete in the UI.
-   **Failure list**: The log identifies failed cells by filename, CSV row, target column, target language, and a safe error message. It never includes source text, translated text, or the API Key, making failures safe to locate and retry.
-   **Unity compatibility scope**: Automated tests use the `Key,Id,Locale...` and CSV (With Comments) structures documented for Unity Localization 1.4, including valid variants with only `Key` or `Id`. Custom columns are preserved, but custom Locale Field Names cannot be identified automatically as language columns, and other package versions have not been verified end-to-end in the Unity Editor.
-   **Structure protection**: The tool preserves .NET/Python/printf placeholders, Unity Smart Strings, ICU expressions, rich-text tags, and line breaks. If translated structure differs, the original target cell is kept and the failure is reported. Nested Smart String/ICU expressions are currently protected as a whole, so branch text inside them is not translated.

## 🧪 Offline Tests

Install the development dependencies and run `python -m pytest`. Tests use a fake
DeepL client, and an automatic fixture blocks network connections, so no real or
billable API is called.

## 🔐 Credential Checks for Contributors

GitHub Actions rejects tracked `config.ini` files and likely credentials. Contributors
can install `pre-commit` and run `pre-commit install` for the same check before each
commit, or run `python scripts/check_secrets.py` manually. The scanner reports only
the file and rule names, never the suspected secret value.

## 📄 License

This project is licensed under the [MIT License](LICENSE).
