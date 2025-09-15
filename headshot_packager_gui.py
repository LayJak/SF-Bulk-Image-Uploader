# --- headshot_packager_gui.py (fixed STATS path) ---
import os, threading, tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from pathlib import Path

import cms_packager  # must be in the same folder

APP_TITLE = "Headshot Packager"
DEFAULT_NAME = "headshots_import.zip"          # output zip filename
DEFAULT_STATS = "headshots_import_STATS.txt"   # stats filename

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.minsize(600, 360)
        self.folder = tk.StringVar(value="")
        self.outzip = tk.StringVar(value="")
        self.stats = tk.StringVar(value="")
        self._build_ui()

    def _build_ui(self):
        frm = tk.Frame(self, padx=12, pady=12)
        frm.pack(fill="both", expand=True)

        tk.Label(frm, text="Image folder (Round/Square/Silhouette files):").grid(row=0, column=0, sticky="w")
        entry = tk.Entry(frm, textvariable=self.folder, width=70)
        entry.grid(row=1, column=0, sticky="we", padx=(0,8))
        tk.Button(frm, text="Browse…", command=self.browse).grid(row=1, column=1, sticky="e")

        tk.Button(frm, text="Build ZIP", command=self.run_packager, width=14).grid(row=2, column=0, sticky="w", pady=(10,6))
        tk.Button(frm, text="Open Output Folder", command=self.open_output, width=18).grid(row=2, column=1, sticky="e", pady=(10,6))

        tk.Label(frm, text="Log:").grid(row=3, column=0, sticky="w", pady=(8,0))
        self.log = scrolledtext.ScrolledText(frm, height=12, state="disabled")
        self.log.grid(row=4, column=0, columnspan=2, sticky="nsew")
        frm.rowconfigure(4, weight=1)
        frm.columnconfigure(0, weight=1)

    def browse(self):
        d = filedialog.askdirectory(title="Select folder of images")
        if d:
            self.folder.set(d)

    def logln(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")
        self.update_idletasks()

    def run_packager(self):
        folder = self.folder.get().strip()
        if not folder:
            messagebox.showwarning(APP_TITLE, "Please choose a folder of images.")
            return
        p = Path(folder)
        if not p.exists():
            messagebox.showerror(APP_TITLE, f"Folder not found:\n{folder}")
            return

        outzip = str(p / DEFAULT_NAME)
        stats = str(p / DEFAULT_STATS)

        self.outzip.set(outzip); self.stats.set(stats)
        self.logln(f"Input: {folder}")
        self.logln(f"Output ZIP: {outzip}")
        self.logln(f"STATS: {stats}")
        self.logln("Running…")

        def worker():
            try:
                z, s = cms_packager.run_packager(folder, outzip, stats_path=stats, title_suffix="")
                self.logln("Success.")
                self.logln(f"ZIP: {z}")
                self.logln(f"STATS: {s}")
                try:
                    os.startfile(Path(z).parent)
                except Exception:
                    pass
                messagebox.showinfo(APP_TITLE, "Done! ZIP and STATS created.")
            except Exception as e:
                self.logln(f"ERROR: {e}")
                messagebox.showerror(APP_TITLE, str(e))

        threading.Thread(target=worker, daemon=True).start()

    def open_output(self):
        target = self.outzip.get() or self.folder.get()
        if target:
            p = Path(target)
            try:
                os.startfile(p if p.is_dir() else p.parent)
            except Exception:
                pass

if __name__ == "__main__":
    App().mainloop()
