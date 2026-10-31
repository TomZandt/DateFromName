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
    """Keep logs in their own folder next to the program, not among the photos."""
    if getattr(sys, "frozen", False):
        base = os.path.dirname(sys.executable)
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "FixPhotoDates logs")


class App:
    def __init__(self, root):
        self.root = root
        self.folder = None
        self.plans = None
        self.skipped = []
        self.changes = []
        self.renumbering = False
        self.renumber_plans = []
        root.title(f"{TITLE}  ({VERSION})")
        root.geometry("1040x720")
        root.minsize(700, 480)

        style = ttk.Style()
        style.configure("Big.TButton", font=BIG_FONT, padding=(20, 12))
        style.configure("Side.TButton", font=FONT, padding=(14, 10))
        style.configure("Treeview", font=("Segoe UI", 10), rowheight=24)
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        style.configure("Update.TFrame", background="#fff4c2")
        style.configure("Update.TLabel", background="#fff4c2", font=FONT)
        style.configure("TCheckbutton", font=FONT)

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
        # Separate job: close the gaps in the numbers after deleting photos.
        self.renumber_button = ttk.Button(buttons, text="Renumber a folder", style="Side.TButton",
                                          command=self.choose_renumber_folder)
        self.renumber_button.pack(side="left", padx=(48, 0))

        options = ttk.Frame(frame)
        options.pack(anchor="w", pady=(12, 0))
        self.add_prefix = tk.BooleanVar(value=False)
        self.month_folders = tk.BooleanVar(value=False)
        self.save_log = tk.BooleanVar(value=False)
        self.option_boxes = [
            ttk.Checkbutton(options, variable=self.add_prefix, command=self.show_plan,
                            text="Add the date to the start of each file name   "
                                 "(e.g. 2026_08_22_0000_IMG-20260822-WA0002.jpeg)"),
            ttk.Checkbutton(options, variable=self.month_folders, command=self.show_plan,
                            text="Put the photos into a folder for each month   (e.g. 2026_08)"),
            ttk.Checkbutton(options, variable=self.save_log,
                            text="Save a list of the changes (a log file)"),
        ]
        for box in self.option_boxes:
            box.pack(anchor="w", pady=2)

        self.message = ttk.Label(frame, font=FONT, wraplength=900, justify="left",
                                 text="Start by clicking “Choose photo folder”.")
        self.message.pack(anchor="w", pady=(16, 8))

        self.progress = ttk.Progressbar(frame, mode="determinate")

        table = ttk.Frame(frame)
        table.pack(fill="both", expand=True)
        columns = ("name", "now", "new", "new_name", "why")
        self.tree = ttk.Treeview(table, columns=columns, show="headings")
        for col, heading, width in zip(columns, ("Photo or video", "Date inside file now", "New date",
                                                 "New name", "What will happen"),
                                       (250, 140, 130, 300, 200)):
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
        self.renumber_button.configure(state=state)
        for box in self.option_boxes:
            box.configure(state=state)
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
        self.renumbering = False
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
        self.plans, self.skipped = plans, skipped
        self.busy(False)
        self.show_plan()

    def show_plan(self):
        """Show what will happen. Runs again whenever an option is ticked."""
        if self.plans is None:
            return
        plans, skipped = self.plans, self.skipped
        core.plan_new_paths(plans, self.folder, self.add_prefix.get(), self.month_folders.get())
        self.changes = [p for p in plans if p.needs_change]
        self.tree.delete(*self.tree.get_children())
        for p in self.changes:
            now = p.embedded.strftime(DATE_FORMAT) if p.embedded else "(none)"
            new_name = os.path.relpath(p.new_path, self.folder) if p.new_path else ""
            why = p.status if p.fixes_date else "Date already right"
            self.tree.insert("", "end", values=(os.path.relpath(p.path, self.folder), now,
                                                p.target.strftime(DATE_FORMAT), new_name, why))
        self.fix_button.configure(state="normal" if self.changes else "disabled")

        date_fixes = sum(1 for p in plans if p.fixes_date)
        moves = sum(1 for p in plans if p.new_path)
        total = len(plans) + len(skipped)
        if total == 0:
            self.say("There are no photos or videos in that folder. Try choosing a different one.")
            return
        lines = [f"Found {total} photos and videos."]
        if len(plans) > date_fixes:
            lines.append(f"✔  {len(plans) - date_fixes} already have the right date.")
        if date_fixes:
            lines.append(f"✎  {date_fixes} will have their date fixed.")
        if moves:
            if self.add_prefix.get() and self.month_folders.get():
                what = "renamed and put into month folders"
            elif self.month_folders.get():
                what = "put into month folders"
            else:
                what = "renamed"
            lines.append(f"↪  {moves} will be {what}.")
        if skipped:
            lines.append(f"–  {len(skipped)} have no date in their name or inside the file "
                         "and will be left alone.")
        if self.changes:
            lines.append("Check the list below, then click “Fix”.")
            self.fix_button.configure(text=f"2.  Fix {len(self.changes)} files")
        else:
            lines.append("Nothing needs changing.")
        self.say("\n".join(lines))

    # --- renumbering (a separate job) ----------------------------------------------

    def choose_renumber_folder(self):
        folder = filedialog.askdirectory(title="Choose the folder to renumber")
        if not folder:
            return
        self.folder = os.path.normpath(folder)
        self.plans = None  # tick boxes don't apply to renumbering
        self.renumbering = True
        self.tree.delete(*self.tree.get_children())
        try:
            self.renumber_plans = core.plan_renumber(self.folder)
        except Exception as exc:
            self.renumber_plans = []
            self.say(f"Sorry, something went wrong reading that folder:\n{exc}")
            return
        self.changes = [p for p in self.renumber_plans if p.needs_change]
        for p in self.changes:
            self.tree.insert("", "end", values=(os.path.relpath(p.path, self.folder), "", "",
                                                os.path.relpath(p.new_path, self.folder), "New number"))
        self.fix_button.configure(state="normal" if self.changes else "disabled")

        if not self.renumber_plans:
            self.say("None of the photos in this folder have numbers at the start of their name yet.\n"
                     "To add them, tick “Add the date to the start of each file name” "
                     "and use “Choose photo folder”.")
        elif not self.changes:
            self.say(f"All {len(self.renumber_plans)} numbered photos and videos are already in order, "
                     "with no gaps. Nothing needs changing.")
        else:
            self.say(f"Found {len(self.renumber_plans)} numbered photos and videos.\n"
                     f"↪  {len(self.changes)} will get a new number to close the gaps. "
                     "Their order stays the same.\n"
                     "Check the list below, then click “Renumber”.")
            self.fix_button.configure(text=f"2.  Renumber {len(self.changes)} files")

    # --- step 2: fix -------------------------------------------------------------

    def fix(self):
        self.busy(True)
        self.say("Working … please wait.")
        threading.Thread(target=self._fix, daemon=True).start()

    def _fix(self):
        plans = self.renumber_plans if self.renumbering else self.plans
        core.apply_plans(plans, self.folder, progress=self.show_progress)
        log_path = None
        if self.save_log.get():
            log_path = os.path.join(log_folder(), f"FixPhotoDates log {datetime.now():%Y-%m-%d %H-%M-%S}.csv")
            try:
                os.makedirs(log_folder(), exist_ok=True)
                core.write_log(plans, log_path)
            except OSError:
                log_path = None
        self.root.after(0, lambda: self._fix_done(log_path))

    def _fix_done(self, log_path):
        failed = [p for p in self.changes if p.error]
        fixed = len(self.changes) - len(failed)
        self.changes = []
        self.plans = None  # the list is out of date now; choose the folder again to recheck
        self.busy(False)
        self.fix_button.configure(text="2.  Fix dates")
        verb = "renumbered" if self.renumbering else "updated"
        lines = [f"Done!  {fixed} photos and videos have been {verb}."]
        if failed:
            lines.append(f"{len(failed)} had a problem (see the list below).")
        lines.append("You can close this window, or choose another folder.")
        if log_path:
            lines.append(f"A record of the changes was saved to: {log_path}")
        self.say("\n".join(lines))
        self.tree.delete(*self.tree.get_children())
        for p in failed:
            self.tree.insert("", "end", values=(os.path.relpath(p.path, self.folder), "", "", "", p.error))


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
