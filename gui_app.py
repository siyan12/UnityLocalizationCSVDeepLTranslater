#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
gui_app.py

Tkinter 图形界面：管理 API Key、测试 API、批量翻译 input 文件夹内的 CSV 到 output 文件夹。
- 启动即确保 ./input 与 ./output 存在
- 后台线程执行翻译，界面不冻结
- 日志区域实时输出进度与错误

运行：
  python gui_app.py

打包为 exe（可选）：
  pip install pyinstaller
  pyinstaller --noconsole --onefile --name CSVTranslator gui_app.py
"""

import os
import threading
import queue
import configparser
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText

from translator_core import (
    ensure_directories,
    test_api_key,
    run_translation_for_folder,
)

APP_TITLE = "CSV Batch Translator v1.1"
INPUT_DIR = "input"
OUTPUT_DIR = "output"
CONFIG_FILE = "config.ini"
CONFIG_SECTION = "deepl"
CONFIG_KEY = "api_key"


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
            "1) Put CSV files into the 'input' folder in the app directory;\n"
            "2) Click 'Start Batch Translation';\n"
            "3) Translated results will be saved to the 'output' folder."
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

    # 配置读写
    def _load_config(self):
        if not os.path.exists(CONFIG_FILE):
            return
        config = configparser.ConfigParser()
        try:
            config.read(CONFIG_FILE, encoding="utf-8")
            if config.has_section(CONFIG_SECTION):
                val = config.get(CONFIG_SECTION, CONFIG_KEY, fallback="")
                self.api_key_var.set(val)
                if val:
                    self._log("Loaded API Key from config.ini.")
        except Exception as e:
            self._log(f"Failed to read config: {e}")

    def _save_config(self):
        config = configparser.ConfigParser()
        config[CONFIG_SECTION] = {CONFIG_KEY: self.api_key_var.get().strip()}
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                config.write(f)
            return True, None
        except Exception as e:
            return False, str(e)

    # 事件处理
    def _on_save_api(self):
        ok, err = self._save_config()
        if ok:
            messagebox.showinfo("Info", "API Key saved to config.ini")
            self._log("API Key saved.")
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
                    f"Summary: files {summary['files']}, rows {summary['rows']}, "
                    f"translated cells {summary['translated_cells']}, errors {summary['errors']}."
                )
            except Exception as e:
                self.log_queue.put(f"任务失败：{e}")
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
                if msg == "__ENABLE__":
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
    app = GuiApp()
    app.mainloop()