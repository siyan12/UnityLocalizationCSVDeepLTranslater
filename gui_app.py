#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui_app.py

Tkinter 图形界面：管理 API Key、测试 API、批量翻译用户数据目录中的 CSV。
- 启动即确保明确的用户数据 input 与 output 目录存在
- 后台线程执行翻译，界面不冻结
- 日志区域实时输出进度与错误

运行：
  python gui_app.py

打包为 exe（可选）：
  pip install pyinstaller
  pyinstaller --noconsole --onefile --name CSVTranslator gui_app.py
"""

import threading
import queue
import sys
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText

from translator_core import (
    ensure_directories,
    safe_error_message,
    test_api_key,
    run_translation_for_folder,
)
from app_storage import (
    CredentialStoreError,
    get_input_dir,
    get_output_dir,
    load_api_key,
    save_api_key,
    verify_credential_store,
)

APP_TITLE = "CSV Batch Translator v1.1"
INPUT_DIR = get_input_dir()
OUTPUT_DIR = get_output_dir()


class GuiApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("720x520")
        self.resizable(True, True)

        # 状态
        self.api_key_var = tk.StringVar()
        self.overwrite_var = tk.BooleanVar(value=False)
        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self.worker_thread: threading.Thread | None = None

        self._build_ui()

        # 确保目录存在
        ensure_directories(INPUT_DIR, OUTPUT_DIR)

        # 读取配置
        self._load_config()

        # 启动日志轮询
        self.after(100, self._poll_log_queue)

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        # API Key 区域
        api_frame = ttk.LabelFrame(self, text="DeepL API Key")
        api_frame.pack(fill=tk.X, **pad)

        entry = ttk.Entry(api_frame, textvariable=self.api_key_var, show="*", width=64)
        entry.grid(row=0, column=0, columnspan=3, sticky="we", padx=8, pady=8)
        api_frame.columnconfigure(0, weight=1)

        save_btn = ttk.Button(api_frame, text="Save API Key", command=self._on_save_api)
        save_btn.grid(row=0, column=3, padx=8, pady=8, sticky="e")

        test_btn = ttk.Button(api_frame, text="Test API Key", command=self._on_test_api)
        test_btn.grid(row=0, column=4, padx=8, pady=8, sticky="e")

        # 说明
        flow_frame = ttk.LabelFrame(self, text="Workflow")
        flow_frame.pack(fill=tk.X, **pad)
        steps = (
            f"1) Put CSV files into:\n   {INPUT_DIR}\n"
            "2) Click 'Start Batch Translation';\n"
            f"3) Translated results will be saved to:\n   {OUTPUT_DIR}"
        )
        ttk.Label(flow_frame, text=steps, justify="left").pack(anchor="w", padx=10, pady=6)

        # 覆盖选项
        opts_frame = ttk.Frame(flow_frame)
        opts_frame.pack(fill=tk.X, padx=8, pady=2)
        overwrite_cb = ttk.Checkbutton(
            opts_frame,
            text="Overwrite existing target cells (by default only fill empty cells)",
            variable=self.overwrite_var,
        )
        overwrite_cb.pack(anchor="w")

        # 开始按钮
        action_frame = ttk.Frame(self)
        action_frame.pack(fill=tk.X, **pad)
        self.start_btn = ttk.Button(action_frame, text="Start Batch Translation", command=self._on_start)
        self.start_btn.pack(pady=4)

        # 日志区域
        log_frame = ttk.LabelFrame(self, text="Logs & Status")
        log_frame.pack(fill=tk.BOTH, expand=True, **pad)

        self.log_text = ScrolledText(log_frame, height=16, state="disabled")
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        self._log("> App started. Please place CSV files into the input folder.")

    # 凭据读写
    def _load_config(self):
        try:
            value = load_api_key() or ""
            self.api_key_var.set(value)
            if value:
                self._log("Loaded API Key from the operating system credential store.")
        except CredentialStoreError as exc:
            self._log(f"Could not load API Key: {exc}")

    def _save_config(self):
        value = self.api_key_var.get().strip()
        if not value:
            return False, "API Key cannot be empty."
        try:
            save_api_key(value)
            return True, None
        except CredentialStoreError as exc:
            return False, str(exc)

    # 事件处理
    def _on_save_api(self):
        ok, err = self._save_config()
        if ok:
            messagebox.showinfo("Info", "API Key saved in the operating system credential store.")
            self._log("API Key saved securely.")
        else:
            messagebox.showerror("Error", f"Save failed: {err}")
            self._log(f"Save failed: {err}")

    def _on_test_api(self):
        key = self.api_key_var.get().strip()
        self._disable_controls(True)
        self._log("Testing API Key ...")
        def run():
            success, msg = test_api_key(key)
            self.log_queue.put(msg)
            self.log_queue.put("__ENABLE__")
            self.log_queue.put("__ALERT_OK__" if success else "__ALERT_FAIL__")
        threading.Thread(target=run, daemon=True).start()

    def _on_start(self):
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showwarning("Warning", "Task is still running, please wait.")
            return
        key = self.api_key_var.get().strip()
        if not key:
            messagebox.showerror("Error", "Please enter and save a valid API Key first.")
            return

        self._disable_controls(True)
        self._log("Starting batch translation...")
        overwrite = self.overwrite_var.get()

        def do_work():
            try:
                summary = run_translation_for_folder(
                    api_key=key,
                    input_dir=INPUT_DIR,
                    output_dir=OUTPUT_DIR,
                    overwrite_existing=overwrite,
                    logger=lambda m: self.log_queue.put(m),
                )
                self.log_queue.put(
                    f"Summary: status {summary['status']}, committed files {summary['files']}, "
                    f"translated cells {summary['translated_cells']}, errors {summary['errors']}."
                )
                self.log_queue.put(("__TRANSLATION_RESULT__", summary))
            except Exception as e:
                safe_error = safe_error_message(e, key)
                self.log_queue.put(f"Task failed: {safe_error}")
                self.log_queue.put(("__TRANSLATION_FATAL__", safe_error))
            finally:
                self.log_queue.put("__ENABLE__")

        self.worker_thread = threading.Thread(target=do_work, daemon=True)
        self.worker_thread.start()

    # UI 辅助
    def _disable_controls(self, busy: bool):
        state = "disabled" if busy else "normal"
        for child in self.winfo_children():
            # 只禁用主要交互控件，日志不禁
            if isinstance(child, ttk.Labelframe) or isinstance(child, ttk.Frame):
                for sub in child.winfo_children():
                    if sub is self.log_text:
                        continue
                    try:
                        sub.configure(state=state)
                    except tk.TclError:
                        pass
        # 单独设置开始按钮
        try:
            self.start_btn.configure(state=state)
        except Exception:
            pass

    def _log(self, msg: str):
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, msg + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    def _poll_log_queue(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                if isinstance(msg, tuple) and msg[0] == "__TRANSLATION_RESULT__":
                    summary = msg[1]
                    status = summary["status"]
                    if status == "success":
                        messagebox.showinfo(
                            "Translation Complete",
                            f"All {summary['successful_files']} file(s) completed successfully.\n"
                            f"Translated cells: {summary['translated_cells']}.",
                        )
                    elif status == "partial":
                        messagebox.showwarning(
                            "Translation Partially Complete",
                            f"Committed files: {summary['files']} "
                            f"(partial: {summary['partial_files']}); "
                            f"failed files: {summary['failed_files']}.\n"
                            f"Failed cells: {len(summary['failed_cells'])}. "
                            "Their previous values were preserved. See the log for details.",
                        )
                    else:
                        messagebox.showerror(
                            "Translation Failed",
                            "No new output files were committed. Existing outputs were not overwritten. "
                            "See the log for details.",
                        )
                elif isinstance(msg, tuple) and msg[0] == "__TRANSLATION_FATAL__":
                    messagebox.showerror("Translation Failed", f"Task failed: {msg[1]}")
                elif msg == "__ENABLE__":
                    self._disable_controls(False)
                elif msg == "__ALERT_OK__":
                    messagebox.showinfo("API Test", "API Key is valid, connected successfully.")
                elif msg == "__ALERT_FAIL__":
                    messagebox.showerror("API Test", "API Key invalid or connection failed.")
                else:
                    self._log(msg)
        except queue.Empty:
            pass
        self.after(100, self._poll_log_queue)


if __name__ == "__main__":
    if "--check-runtime" in sys.argv:
        try:
            verify_credential_store()
        except CredentialStoreError:
            raise SystemExit(1)
        raise SystemExit(0)
    app = GuiApp()
    app.mainloop()
