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
  pyinstaller --clean --noconfirm CSVTranslator.spec
"""

import threading
import queue
import sys
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText

from app_version import __version__
from translator_core import (
    TranslationCancelled,
    ensure_directories,
    estimate_translation_for_folder,
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

APP_TITLE = f"CSV Batch Translator v{__version__}"
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
        self.cancel_event: threading.Event | None = None

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
        self.start_btn.pack(side=tk.LEFT, expand=True, pady=4)
        self.cancel_btn = ttk.Button(
            action_frame,
            text="Cancel",
            command=self._on_cancel,
            state="disabled",
        )
        self.cancel_btn.pack(side=tk.LEFT, expand=True, pady=4)

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
            self.log_queue.put(("__API_TEST_RESULT__", success, msg))
        threading.Thread(target=run, daemon=True).start()

    def _on_start(self):
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showwarning("Warning", "Task is still running, please wait.")
            return
        key = self.api_key_var.get().strip()
        if not key:
            messagebox.showerror("Error", "Please enter and save a valid API Key first.")
            return

        self._disable_controls(True, cancellable=True)
        self._log("Scanning input files for a translation estimate...")
        overwrite = self.overwrite_var.get()
        self.cancel_event = threading.Event()
        cancel_event = self.cancel_event

        def do_work():
            try:
                estimate = estimate_translation_for_folder(
                    INPUT_DIR,
                    overwrite_existing=overwrite,
                    cancel_event=cancel_event,
                )
                decision_event = threading.Event()
                decision = {"proceed": False}
                self.log_queue.put(
                    ("__TRANSLATION_ESTIMATE__", estimate, decision_event, decision)
                )
                while not decision_event.wait(0.1):
                    if cancel_event.is_set():
                        raise TranslationCancelled(
                            "Translation cancelled before confirmation."
                        )
                if not decision["proceed"]:
                    raise TranslationCancelled("Translation cancelled before API calls.")

                self.log_queue.put("Starting batch translation...")
                summary = run_translation_for_folder(
                    api_key=key,
                    input_dir=INPUT_DIR,
                    output_dir=OUTPUT_DIR,
                    overwrite_existing=overwrite,
                    logger=lambda m: self.log_queue.put(m),
                    cancel_event=cancel_event,
                    expected_input_snapshot=estimate["input_snapshot"],
                )
                self.log_queue.put(
                    f"Summary: status {summary['status']}, committed files {summary['files']}, "
                    f"translated cells {summary['translated_cells']}, errors {summary['errors']}."
                )
                self.log_queue.put(("__TRANSLATION_RESULT__", summary))
            except TranslationCancelled:
                self.log_queue.put(
                    (
                        "__TRANSLATION_RESULT__",
                        {"status": "cancelled", "files": 0, "cancelled": True},
                    )
                )
            except Exception as e:
                safe_error = safe_error_message(e, key)
                self.log_queue.put(f"Task failed: {safe_error}")
                self.log_queue.put(("__TRANSLATION_FATAL__", safe_error))
            finally:
                self.log_queue.put("__ENABLE__")

        self.worker_thread = threading.Thread(target=do_work, daemon=True)
        self.worker_thread.start()

    def _on_cancel(self):
        if self.cancel_event is not None:
            self.cancel_event.set()
            self.cancel_btn.configure(state="disabled")
            self._log(
                "Cancellation requested; an in-flight DeepL request may finish, "
                "but the current file will not be committed."
            )

    # UI 辅助
    def _disable_controls(self, busy: bool, cancellable: bool = False):
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
            self.cancel_btn.configure(
                state="normal" if busy and cancellable else "disabled"
            )
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
                    if status == "cancelled":
                        messagebox.showinfo(
                            "Translation Cancelled",
                            f"Translation was cancelled. Completed files kept: "
                            f"{summary.get('files', 0)}. The current file was not committed.",
                        )
                    elif status == "success":
                        messagebox.showinfo(
                            "Translation Complete",
                            f"All {summary['successful_files']} file(s) completed successfully.\n"
                            f"Translated cells: {summary['translated_cells']}.",
                        )
                    elif status == "partial":
                        fatal_detail = (
                            f"\n\n{summary['fatal_error']}"
                            if summary.get("fatal_error")
                            else ""
                        )
                        messagebox.showwarning(
                            "Translation Partially Complete",
                            f"Committed files: {summary['files']} "
                            f"(partial: {summary['partial_files']}); "
                            f"failed files: {summary['failed_files']}.\n"
                            f"Failed cells: {len(summary['failed_cells'])}. "
                            "Their previous values were preserved. See the log for details."
                            + fatal_detail,
                        )
                    else:
                        fatal_detail = (
                            f"\n\n{summary['fatal_error']}"
                            if summary.get("fatal_error")
                            else ""
                        )
                        messagebox.showerror(
                            "Translation Failed",
                            "No new output files were committed. Existing outputs were not overwritten. "
                            "See the log for details." + fatal_detail,
                        )
                elif isinstance(msg, tuple) and msg[0] == "__TRANSLATION_ESTIMATE__":
                    estimate, decision_event, decision = msg[1:]
                    try:
                        if self.cancel_event is not None and self.cancel_event.is_set():
                            decision["proceed"] = False
                        else:
                            error_note = (
                                f"\nFiles with validation errors: {len(estimate['errors'])}."
                                if estimate["errors"]
                                else ""
                            )
                            decision["proceed"] = messagebox.askyesno(
                                "Confirm Translation",
                                f"Eligible cells: {estimate['eligible_cells']}\n"
                                f"Target languages: {estimate['target_languages']}\n"
                                f"Characters before cache: {estimate['characters']:,}\n"
                                f"Estimated characters sent after task cache: "
                                f"{estimate['unique_characters']:,}\n"
                                f"Unique translation requests: {estimate['unique_requests']}"
                                f"{error_note}\n\nContinue?",
                            )
                    finally:
                        decision_event.set()
                elif isinstance(msg, tuple) and msg[0] == "__TRANSLATION_FATAL__":
                    messagebox.showerror("Translation Failed", f"Task failed: {msg[1]}")
                elif isinstance(msg, tuple) and msg[0] == "__API_TEST_RESULT__":
                    if msg[1]:
                        messagebox.showinfo("API Test", msg[2])
                    else:
                        messagebox.showerror("API Test", msg[2])
                elif msg == "__ENABLE__":
                    self._disable_controls(False)
                    self.cancel_event = None
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
