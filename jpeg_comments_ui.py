"""tkinter UI for the JPEG comment caption burner.

Shows a file list with comment markers and side-by-side previews of the
original image and the captioned result (rendered in-memory, not saved).

Run with:  python jpeg_comments_ui.py
"""

import contextlib
import io
import os
import threading
import tkinter as tk
from tkinter import filedialog, ttk

from PIL import Image, ImageTk

import jpeg_comments

PREVIEW_BOX = (340, 380)


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


def make_preview_panel(parent, title):
    """Fixed-size frame that centers a thumbnail image inside."""
    frame = ttk.LabelFrame(parent, text=title, padding=4)
    holder = tk.Frame(frame, width=PREVIEW_BOX[0], height=PREVIEW_BOX[1])
    holder.pack_propagate(False)
    holder.pack()
    label = ttk.Label(holder, text="No preview")
    label.place(relx=0.5, rely=0.5, anchor="center")
    return frame, label


def thumbnail(img):
    """Return a copy of img scaled to fit inside PREVIEW_BOX."""
    im = img.copy()
    im.thumbnail(PREVIEW_BOX, Image.LANCZOS)
    return im


class JpegCommentsApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("JPEG Comments")
        self.minsize(900, 560)

        self.folder_var = tk.StringVar()
        self.quality_var = tk.IntVar(value=95)
        self.comment_var = tk.StringVar(value="Select a file to preview.")

        self.file_names = []          # parallel to the listbox items
        self.comments = {}            # name -> comment text or "" (cache)
        self.preview_gen = 0          # guards against stale async previews
        self._orig_photo = None       # keep PhotoImage refs alive
        self._result_photo = None

        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")

        ttk.Label(top, text="Folder:").pack(side="left")
        entry = ttk.Entry(top, textvariable=self.folder_var)
        entry.pack(side="left", fill="x", expand=True, padx=(4, 4))
        entry.bind("<Return>", self.load_folder_from_entry)
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

        main = ttk.Frame(self, padding=(8, 0, 8, 4))
        main.pack(fill="both", expand=True)

        left = ttk.Frame(main)
        left.pack(side="left", fill="y")
        ttk.Label(left, text="Files").pack(anchor="w")
        list_frame = ttk.Frame(left)
        list_frame.pack(fill="both", expand=True)
        self.file_list = tk.Listbox(
            list_frame, width=34, exportselection=False, activestyle="none"
        )
        scroll = ttk.Scrollbar(list_frame, orient="vertical", command=self.file_list.yview)
        self.file_list.configure(yscrollcommand=scroll.set)
        self.file_list.pack(side="left", fill="both", expand=True)
        scroll.pack(side="left", fill="y")
        self.file_list.bind("<<ListboxSelect>>", self.on_select)

        right = ttk.Frame(main, padding=(8, 0, 0, 0))
        right.pack(side="left", fill="both", expand=True)

        previews = ttk.Frame(right)
        previews.pack(fill="both", expand=True)
        orig_frame, self.orig_label = make_preview_panel(previews, "Original")
        orig_frame.pack(side="left", fill="both", expand=True, padx=(0, 6))
        result_frame, self.result_label = make_preview_panel(previews, "With caption")
        result_frame.pack(side="left", fill="both", expand=True)

        ttk.Label(
            right, textvariable=self.comment_var, wraplength=PREVIEW_BOX[0] * 2 + 16
        ).pack(anchor="w", pady=(6, 0))

        self.log = tk.Text(self, height=8, state="disabled", wrap="word")
        self.log.pack(fill="x", padx=8, pady=(0, 8))

    # --- folder handling -------------------------------------------------

    def browse(self):
        folder = filedialog.askdirectory()
        if folder:
            self.load_folder(folder)

    def load_folder_from_entry(self, _event=None):
        folder = self.folder_var.get().strip()
        if folder and os.path.isdir(folder):
            self.load_folder(folder)

    def load_folder(self, folder):
        self.folder_var.set(folder)
        self.file_names = sorted(
            name for name in os.listdir(folder)
            if name.lower().endswith(jpeg_comments.JPEG_EXTENSIONS)
            and os.path.isfile(os.path.join(folder, name))
        )
        self.comments.clear()
        self.file_list.delete(0, "end")
        for name in self.file_names:
            self.file_list.insert("end", "   " + name)
        self._clear_previews()
        self.comment_var.set(
            f"{len(self.file_names)} JPEGs - scanning for comments..."
        )
        threading.Thread(target=self._scan_comments, args=(folder,), daemon=True).start()

    def _scan_comments(self, folder):
        """Background pass that marks which files contain a comment."""
        for index, name in enumerate(self.file_names):
            comment = jpeg_comments.get_jpeg_comment(os.path.join(folder, name))
            self.comments[name] = comment
            self.after(0, self._mark_file, index, name, bool(comment))
        self.after(
            0,
            self.comment_var.set,
            f"{len(self.file_names)} JPEGs - "
            f"{sum(1 for v in self.comments.values() if v)} with comments.",
        )

    def _mark_file(self, index, name, has_comment):
        if index < self.file_list.size() and self.file_names[index] == name:
            mark = "\u2713 " if has_comment else "\u2013 "
            self.file_list.delete(index)
            self.file_list.insert(index, mark + name)

    # --- previews ---------------------------------------------------------

    def _clear_previews(self):
        self.preview_gen += 1
        self.orig_label.configure(image="", text="No preview")
        self.result_label.configure(image="", text="No preview")
        self._orig_photo = None
        self._result_photo = None

    def on_select(self, _event):
        selection = self.file_list.curselection()
        if not selection:
            return
        name = self.file_names[selection[0]]
        folder = self.folder_var.get().strip()
        if not folder:
            return
        self.preview_gen += 1
        gen = self.preview_gen
        threading.Thread(
            target=self._load_preview, args=(gen, folder, name), daemon=True
        ).start()

    def _load_preview(self, gen, folder, name):
        path = os.path.join(folder, name)
        try:
            with Image.open(path) as img:
                img.load()
                original = img.copy()
        except OSError:
            self.after(0, self._preview_error, gen, name)
            return
        if name not in self.comments:
            self.comments[name] = jpeg_comments.get_jpeg_comment(path)
        comment = self.comments[name]
        result = (
            jpeg_comments.burn_comment(original, comment, None, 0)
            if comment else None
        )
        self.after(0, self._show_preview, gen, name, original, result, comment)

    def _preview_error(self, gen, name):
        if gen != self.preview_gen:
            return
        self.orig_label.configure(image="", text="Cannot open image")
        self.result_label.configure(image="", text="")
        self.comment_var.set(f"{name}: unreadable file")

    def _show_preview(self, gen, name, original, result, comment):
        if gen != self.preview_gen:
            return
        self._orig_photo = ImageTk.PhotoImage(thumbnail(original))
        self.orig_label.configure(image=self._orig_photo, text="")
        if result is not None:
            self._result_photo = ImageTk.PhotoImage(thumbnail(result))
            self.result_label.configure(image=self._result_photo, text="")
            self.comment_var.set(f"{name}: {comment}")
        else:
            self._result_photo = None
            self.result_label.configure(image="", text="No comment")
            self.comment_var.set(f"{name}: (no comment)")

    # --- batch processing -------------------------------------------------

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
