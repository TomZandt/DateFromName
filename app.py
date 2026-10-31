"""Simple window for fixing photo dates. Built into FixPhotoDates.exe."""

import os
import sys
import threading
import tkinter as tk
from datetime import datetime
from tkinter import filedialog, ttk

import datefromname as core
import updater
from _version import VERSION

TITLE = "Fix Photo Dates"
FONT = ("Segoe UI", 12)
BIG_FONT = ("Segoe UI", 14, "bold")
DATE_FORMAT = "%d/%m/%Y  %H:%M"


def log_folder():
    """Keep the log next to the program, not among the photos."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


class App:
    def __init__(self, root):
        self.root = root
        self.folder = None
        self.changes = []
        root.title(f"{TITLE}  ({VERSION})")
        root.geometry("980x640")
        root.minsize(700, 480)

        style = ttk.Style()
        style.configure("Big.TButton", font=BIG_FONT, padding=(20, 12))
        style.configure("Treeview", font=("Segoe UI", 10), rowheight=24)
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        style.configure("Update.TFrame", background="#fff4c2")
        style.configure("Update.TLabel", background="#fff4c2", font=FONT)

        self.update_bar = ttk.Frame(root, style="Update.TFrame", padding=(20, 10))
        self.update_text = ttk.Label(self.update_bar, style="Update.TLabel")
        self.update_text.pack(side="left")
        self.update_button = ttk.Button(self.update_bar, text="Update now", command=self.install_update)
        self.update_button.pack(side="right")

        frame = ttk.Frame(root, padding=20)
        frame.pack(fill="both", expand=True)
        self.main_frame = frame

        ttk.Label(frame, text=TITLE, font=("Segoe UI", 20, "bold")).pack(anchor="w")
        ttk.Label(
            frame, font=FONT, wraplength=900, justify="left",
            text="Some photos show the day they were downloaded instead of the day they were "
                 "taken. This puts the right date back, using the date in each file's name. "
                 "The pictures themselves are not changed.",
        ).pack(anchor="w", pady=(4, 16))

        buttons = ttk.Frame(frame)
        buttons.pack(anchor="w")
        self.choose_button = ttk.Button(buttons, text="1.  Choose photo folder", style="Big.TButton",
                                        command=self.choose_folder)
        self.choose_button.pack(side="left")
        self.fix_button = ttk.Button(buttons, text="2.  Fix dates", style="Big.TButton",
                                     command=self.fix, state="disabled")
        self.fix_button.pack(side="left", padx=(16, 0))

        self.message = ttk.Label(frame, font=FONT, wraplength=900, justify="left",
                                 text="Start by clicking “Choose photo folder”.")
        self.message.pack(anchor="w", pady=(16, 8))

        self.progress = ttk.Progressbar(frame, mode="determinate")

        table = ttk.Frame(frame)
        table.pack(fill="both", expand=True)
        columns = ("name", "now", "new", "why")
        self.tree = ttk.Treeview(table, columns=columns, show="headings")
        for col, heading, width in zip(columns, ("Photo or video", "Date inside file now", "New date", "What will happen"),
                                       (330, 170, 150, 260)):
            self.tree.heading(col, text=heading)
            self.tree.column(col, width=width, anchor="w")
        scroll = ttk.Scrollbar(table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        if updater.can_update():
            updater.remove_old_version()
            threading.Thread(target=self._check_for_update, daemon=True).start()

    # --- updates -----------------------------------------------------------------

    def _check_for_update(self):
        found = updater.check_for_update()
        if found:
            self.root.after(0, lambda: self._offer_update(*found))

    def _offer_update(self, tag, url):
        self.update_url = url
        self.update_text.configure(text=f"A newer version of this program ({tag}) is available.")
        self.update_bar.pack(fill="x", before=self.main_frame)

    def install_update(self):
        self.update_button.configure(state="disabled")
        self.update_text.configure(text="Downloading the new version … the program will restart by itself.")
        threading.Thread(target=self._install_update, daemon=True).start()

    def _install_update(self):
        try:
            updater.install_update(self.update_url)
        except Exception:
            self.root.after(0, self._update_failed)
            return
        self.root.after(0, self.root.destroy)

    def _update_failed(self):
        import webbrowser
        self.update_text.configure(text="The update could not be installed automatically. "
                                        "The download page has been opened instead.")
        webbrowser.open(updater.RELEASES_PAGE)

    # --- helpers -----------------------------------------------------------

    def say(self, text):
        self.message.configure(text=text)

    def show_progress(self, done, total):
        self.root.after(0, lambda: self.progress.configure(maximum=total, value=done))

    def busy(self, is_busy):
        state = "disabled" if is_busy else "normal"
        self.choose_button.configure(state=state)
        self.fix_button.configure(state="disabled" if is_busy or not self.changes else "normal")
        if is_busy:
            self.progress.configure(value=0)
            self.progress.pack(fill="x", pady=(0, 8), before=self.tree.master)
        else:
            self.progress.pack_forget()

    # --- step 1: look at the folder ------------------------------------------

    def choose_folder(self):
        folder = filedialog.askdirectory(title="Choose the folder with the photos")
        if not folder:
            return
        self.folder = os.path.normpath(folder)
        self.changes = []
        self.tree.delete(*self.tree.get_children())
        self.say(f"Looking at the photos in {self.folder} …")
        self.busy(True)
        threading.Thread(target=self._scan, daemon=True).start()

    def _scan(self):
        try:
            plans, skipped = core.plan_folder(self.folder, progress=self.show_progress)
        except Exception as exc:
            self.root.after(0, lambda: self._scan_failed(exc))
            return
        self.root.after(0, lambda: self._scan_done(plans, skipped))

    def _scan_failed(self, exc):
        self.busy(False)
        self.say(f"Sorry, something went wrong reading that folder:\n{exc}")

    def _scan_done(self, plans, skipped):
        self.plans = plans
        self.changes = [p for p in plans if p.needs_change]
        correct = len(plans) - len(self.changes)
        for p in self.changes:
            now = p.embedded.strftime(DATE_FORMAT) if p.embedded else "(none)"
            self.tree.insert("", "end", values=(os.path.relpath(p.path, self.folder), now,
                                                p.target.strftime(DATE_FORMAT), p.status))
        self.busy(False)

        total = len(plans) + len(skipped)
        if total == 0:
            self.say("There are no photos or videos in that folder. Try choosing a different one.")
        elif not self.changes:
            self.say(f"Good news: all {len(plans)} photos and videos already have the right date. "
                     "Nothing needs fixing.")
        else:
            lines = [f"Found {total} photos and videos.",
                     f"✔  {correct} already have the right date.",
                     f"✎  {len(self.changes)} will be fixed (listed below)."]
            if skipped:
                lines.append(f"–  {len(skipped)} have no date in their name and will be left alone.")
            lines.append("Click “Fix dates” to fix them.")
            self.say("\n".join(lines))
            self.fix_button.configure(text=f"2.  Fix {len(self.changes)} dates")

    # --- step 2: fix -------------------------------------------------------------

    def fix(self):
        self.busy(True)
        self.say("Fixing dates … please wait.")
        threading.Thread(target=self._fix, daemon=True).start()

    def _fix(self):
        for i, plan in enumerate(self.changes, 1):
            core.apply_plan(plan)
            self.show_progress(i, len(self.changes))
        log_path = os.path.join(log_folder(), f"FixPhotoDates log {datetime.now():%Y-%m-%d %H-%M-%S}.csv")
        try:
            core.write_log(self.plans, log_path)
        except OSError:
            log_path = None
        self.root.after(0, lambda: self._fix_done(log_path))

    def _fix_done(self, log_path):
        failed = [p for p in self.changes if p.error]
        fixed = len(self.changes) - len(failed)
        self.changes = []
        self.busy(False)
        self.fix_button.configure(text="2.  Fix dates")
        lines = [f"Done!  {fixed} photos and videos now have the right date."]
        if failed:
            lines.append(f"{len(failed)} had a problem (see the list below).")
        lines.append("You can close this window, or choose another folder.")
        if log_path:
            lines.append(f"A record of the changes was saved to: {log_path}")
        self.say("\n".join(lines))
        self.tree.delete(*self.tree.get_children())
        for p in failed:
            self.tree.insert("", "end", values=(os.path.relpath(p.path, self.folder), "", "", p.error))


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
