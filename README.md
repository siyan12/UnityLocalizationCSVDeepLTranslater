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

-   **专为 Unity 设计**：完美适配 Unity Localization 插件导出的 CSV 格式。
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
    -   选择源语言、目标语言，然后点击“开始翻译”。
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
-   **CSV 格式**：请确保你的 CSV 文件来自 Unity Localization 插件，并包含 `Key` 列和源语言列（例如 `en`）。

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

-   **Designed for Unity**: Perfectly compatible with the CSV format exported by the Unity Localization package.
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
    -   Select the source and target languages, then click "Start Translation."
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
-   **CSV Format**: Ensure your CSV file is from the Unity Localization package and contains a `Key` column and a source language column (e.g., `en`).

## 🔐 Credential Checks for Contributors

GitHub Actions rejects tracked `config.ini` files and likely credentials. Contributors
can install `pre-commit` and run `pre-commit install` for the same check before each
commit, or run `python scripts/check_secrets.py` manually. The scanner reports only
the file and rule names, never the suspected secret value.

## 📄 License

This project is licensed under the [MIT License](LICENSE).
