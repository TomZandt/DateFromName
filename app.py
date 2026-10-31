"""Simple window for fixing photo dates. Built into FixPhotoDates.exe.

Two tabs, each a two-step job read from top to bottom: choose a folder
(which only previews), check the list, then click the button under it.
"""

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


class Tab:
    """One job: explanation, choose a folder, preview list, do-it button."""

    title = ""
    intro = ""
    choose_text = "1.  Choose photo folder"
    go_text = ""
    start_text = "Start by clicking “1.  Choose photo folder”."
    columns = ()  # (id, heading, width)

    def __init__(self, app, notebook):
        self.app = app
        self.folder = None
        self.plans = None
        self.changes = []

        self.frame = ttk.Frame(notebook, padding=20)
        notebook.add(self.frame, text=f"  {self.title}  ")
        ttk.Label(self.frame, font=FONT, wraplength=960, justify="left", text=self.intro).pack(anchor="w")
        self.choose_button = ttk.Button(self.frame, text=self.choose_text, style="Big.TButton",
                                        command=self.choose_folder)
        self.choose_button.pack(anchor="w", pady=(14, 0))
        self.option_boxes = self.build_options()

        self.message = ttk.Label(self.frame, font=FONT, wraplength=960, justify="left", text=self.start_text)
        self.message.pack(anchor="w", pady=(14, 8))
        self.progress = ttk.Progressbar(self.frame, mode="determinate")

        self.table = ttk.Frame(self.frame)
        self.table.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(self.table, columns=[c[0] for c in self.columns], show="headings", height=8)
        for col, heading, width in self.columns:
            self.tree.heading(col, text=heading)
            self.tree.column(col, width=width, anchor="w")
        scroll = ttk.Scrollbar(self.table, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        self.go_button = ttk.Button(self.frame, text=self.go_text, style="Big.TButton",
                                    command=self.go, state="disabled")
        self.go_button.pack(anchor="w", pady=(12, 0))

    # --- to fill in for each job ---------------------------------------------------

    def build_options(self):
        return []

    def scan(self):
        """Look at self.folder (in a background thread) and return the plans."""
        raise NotImplementedError

    def show_plan(self):
        raise NotImplementedError

    # --- shared ------------------------------------------------------------------

    def say(self, text):
        self.message.configure(text=text)

    def show_progress(self, done, total):
        self.app.root.after(0, lambda: self.progress.configure(maximum=total, value=done))

    def busy(self, is_busy):
        state = "disabled" if is_busy else "normal"
        self.choose_button.configure(state=state)
        for box in self.option_boxes:
            box.configure(state=state)
        self.go_button.configure(state="disabled" if is_busy or not self.changes else "normal")
        if is_busy:
            self.progress.configure(value=0)
            self.progress.pack(fill="x", pady=(0, 8), before=self.table)
        else:
            self.progress.pack_forget()

    def show_rows(self, rows):
        self.tree.delete(*self.tree.get_children())
        for row in rows:
            self.tree.insert("", "end", values=row)

    def relative(self, path):
        return os.path.relpath(path, self.folder)

    def choose_folder(self):
        folder = filedialog.askdirectory(title="Choose the folder with the photos")
        if not folder:
            return
        self.folder = os.path.normpath(folder)
        self.plans = None
        self.changes = []
        self.show_rows([])
        self.say(f"Looking at the photos in {self.folder} …")
        self.busy(True)
        threading.Thread(target=self._scan, daemon=True).start()

    def _scan(self):
        try:
            plans = self.scan()
        except Exception as exc:
            self.app.root.after(0, lambda: self._scan_failed(exc))
            return
        self.app.root.after(0, lambda: self._scan_done(plans))

    def _scan_failed(self, exc):
        self.busy(False)
        self.say(f"Sorry, something went wrong reading that folder:\n{exc}")

    def _scan_done(self, plans):
        self.plans = plans
        self.busy(False)
        self.show_plan()

    def set_changes(self, changes, go_text):
        self.changes = changes
        self.go_button.configure(text=go_text if changes else self.go_text,
                                 state="normal" if changes else "disabled")

    def go(self):
        self.busy(True)
        self.say("Working … please wait.")
        threading.Thread(target=self._go, daemon=True).start()

    def _go(self):
        core.apply_plans(self.plans, self.folder, progress=self.show_progress)
        log_path = None
        if self.app.save_log.get():
            log_path = os.path.join(log_folder(), f"FixPhotoDates log {datetime.now():%Y-%m-%d %H-%M-%S}.csv")
            try:
                os.makedirs(log_folder(), exist_ok=True)
                core.write_log(self.plans, log_path)
            except OSError:
                log_path = None
        self.app.root.after(0, lambda: self._go_done(log_path))

    def _go_done(self, log_path):
        failed = [p for p in self.changes if p.error]
        done = len(self.changes) - len(failed)
        self.plans = None  # out of date now; choose the folder again to recheck
        self.set_changes([], "")
        self.busy(False)
        lines = [f"Done!  {done} photos and videos have been {self.done_verb}."]
        if failed:
            lines.append(f"{len(failed)} had a problem (see the list below).")
        lines.append("You can close this window, or choose another folder.")
        if log_path:
            lines.append(f"A record of the changes was saved to: {log_path}")
        self.say("\n".join(lines))
        blanks = [""] * (len(self.columns) - 2)
        self.show_rows([(self.relative(p.path), *blanks, p.error) for p in failed])


class FixTab(Tab):
    title = "Fix dates"
    intro = ("Some photos show the day they were downloaded instead of the day they were taken. "
             "This puts the right date back, using the date in each file's name. "
             "The pictures themselves are not changed.")
    go_text = "2.  Fix"
    done_verb = "updated"
    columns = (("name", "Photo or video", 230), ("now", "Date inside file now", 130),
               ("new", "New date", 120), ("new_name", "New name", 280), ("why", "What will happen", 170))

    def build_options(self):
        options = ttk.Frame(self.frame)
        options.pack(anchor="w", pady=(12, 0))
        ttk.Label(options, text="Also:", font=FONT).grid(row=0, column=0, sticky="nw", padx=(0, 10))
        self.add_prefix = tk.BooleanVar(value=False)
        self.month_folders = tk.BooleanVar(value=False)
        boxes = [
            ttk.Checkbutton(options, variable=self.add_prefix, command=self.show_plan,
                            text="Add the date to the start of each file name   "
                                 "(e.g. 2026_08_22_0000_IMG-20260822-WA0002.jpeg)"),
            ttk.Checkbutton(options, variable=self.month_folders, command=self.show_plan,
                            text="Put the photos into a folder for each month   (e.g. 2026_08)"),
        ]
        for row, box in enumerate(boxes):
            box.grid(row=row, column=1, sticky="w", pady=2)
        return boxes

    def scan(self):
        plans, self.skipped = core.plan_folder(self.folder, progress=self.show_progress)
        return plans

    def show_plan(self):
        """Show what will happen. Runs again whenever an option is ticked."""
        if self.plans is None:
            return
        plans, skipped = self.plans, self.skipped
        core.plan_new_paths(plans, self.folder, self.add_prefix.get(), self.month_folders.get())
        changes = [p for p in plans if p.needs_change]
        self.show_rows([
            (self.relative(p.path),
             p.embedded.strftime(DATE_FORMAT) if p.embedded else "(none)",
             p.target.strftime(DATE_FORMAT),
             self.relative(p.new_path) if p.new_path else "",
             p.status if p.fixes_date else "Date already right")
            for p in changes])
        self.set_changes(changes, f"2.  Fix {len(changes)} files")

        total = len(plans) + len(skipped)
        if total == 0:
            self.say("There are no photos or videos in that folder. Try choosing a different one.")
            return
        date_fixes = sum(1 for p in plans if p.fixes_date)
        moves = sum(1 for p in plans if p.new_path)
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
        if changes:
            lines.append("Check the list below, then click “Fix” at the bottom.")
        else:
            lines.append("Nothing needs changing.")
        self.say("\n".join(lines))


class RenumberTab(Tab):
    title = "Renumber"
    intro = ("Deleted some photos you didn't want? This closes the gaps in the numbers at the start of "
             "the file names (0000, 0001, 0002 …), keeping the photos in the same order. "
             "Nothing else is changed.")
    choose_text = "1.  Choose folder"
    start_text = "Start by clicking “1.  Choose folder”."
    go_text = "2.  Renumber"
    done_verb = "renumbered"
    columns = (("name", "Photo or video", 480), ("new_name", "New name", 480))

    def scan(self):
        return core.plan_renumber(self.folder)

    def show_plan(self):
        plans = self.plans
        changes = [p for p in plans if p.needs_change]
        self.show_rows([(self.relative(p.path), self.relative(p.new_path)) for p in changes])
        self.set_changes(changes, f"2.  Renumber {len(changes)} files")
        if not plans:
            self.say("None of the photos in this folder have numbers at the start of their name yet.\n"
                     "To add them, use the “Fix dates” tab and tick "
                     "“Add the date to the start of each file name”.")
        elif not changes:
            self.say(f"All {len(plans)} numbered photos and videos are already in order, "
                     "with no gaps. Nothing needs changing.")
        else:
            self.say(f"Found {len(plans)} numbered photos and videos.\n"
                     f"↪  {len(changes)} will get a new number to close the gaps. "
                     "Their order stays the same.\n"
                     "Check the list below, then click “Renumber” at the bottom.")


class App:
    def __init__(self, root):
        self.root = root
        root.title(f"{TITLE}  ({VERSION})")
        root.geometry("1060x800")
        root.minsize(760, 560)

        style = ttk.Style()
        style.configure("Big.TButton", font=BIG_FONT, padding=(20, 12))
        style.configure("TNotebook.Tab", font=BIG_FONT, padding=(18, 8))
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

        self.main_frame = ttk.Frame(root, padding=(20, 16, 20, 12))
        self.main_frame.pack(fill="both", expand=True)
        ttk.Label(self.main_frame, text=TITLE, font=("Segoe UI", 20, "bold")).pack(anchor="w", pady=(0, 10))

        notebook = ttk.Notebook(self.main_frame)
        notebook.pack(fill="both", expand=True)
        self.fix_tab = FixTab(self, notebook)
        self.renumber_tab = RenumberTab(self, notebook)

        self.save_log = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.main_frame, variable=self.save_log,
                        text="Save a list of the changes (a log file)").pack(anchor="w", pady=(10, 0))

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


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
