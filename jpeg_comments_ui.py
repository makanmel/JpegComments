"""Minimal tkinter UI for the JPEG comment caption burner.

Run with:  python jpeg_comments_ui.py
"""

import contextlib
import io
import os
import threading
import tkinter as tk
from tkinter import filedialog, ttk

import jpeg_comments


class TextRedirect(io.StringIO):
    """Redirect print() output from the worker thread into the log widget."""

    def __init__(self, widget):
        super().__init__()
        self.widget = widget

    def write(self, text):
        self.widget.after(0, self._append, text)

    def _append(self, text):
        self.widget.configure(state="normal")
        self.widget.insert("end", text)
        self.widget.see("end")
        self.widget.configure(state="disabled")


class JpegCommentsApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("JPEG Comments")
        self.minsize(560, 380)

        self.folder_var = tk.StringVar()
        self.quality_var = tk.IntVar(value=95)

        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")

        ttk.Label(top, text="Folder:").pack(side="left")
        entry = ttk.Entry(top, textvariable=self.folder_var)
        entry.pack(side="left", fill="x", expand=True, padx=(4, 4))
        ttk.Button(top, text="Browse...", command=self.browse).pack(side="left")

        options = ttk.Frame(self, padding=(8, 0, 8, 8))
        options.pack(fill="x")

        ttk.Label(options, text="Quality:").pack(side="left")
        ttk.Spinbox(options, from_=50, to=100, width=5, textvariable=self.quality_var).pack(
            side="left", padx=(4, 16)
        )
        self.list_button = ttk.Button(
            options, text="List comments", command=lambda: self.run(list_only=True)
        )
        self.list_button.pack(side="left")
        self.process_button = ttk.Button(
            options, text="Burn captions", command=lambda: self.run(list_only=False)
        )
        self.process_button.pack(side="left", padx=(8, 0))

        self.log = tk.Text(self, height=14, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True, padx=8, pady=(0, 8))

    def browse(self):
        folder = filedialog.askdirectory()
        if folder:
            self.folder_var.set(folder)

    def run(self, list_only):
        folder = self.folder_var.get().strip()
        if not folder or not os.path.isdir(folder):
            print("Select a valid folder first.", file=TextRedirect(self.log))
            return
        self.list_button.configure(state="disabled")
        self.process_button.configure(state="disabled")
        threading.Thread(
            target=self._worker, args=(folder, list_only), daemon=True
        ).start()

    def _worker(self, folder, list_only):
        output_dir = os.path.join(folder, "captioned")
        with contextlib.redirect_stdout(TextRedirect(self.log)):
            jpeg_comments.process_folder(
                folder, output_dir,
                font_path=None, font_size=0,
                quality=self.quality_var.get(),
                list_only=list_only,
            )
        self.after(0, self._on_done)

    def _on_done(self):
        self.list_button.configure(state="normal")
        self.process_button.configure(state="normal")


if __name__ == "__main__":
    JpegCommentsApp().mainloop()
