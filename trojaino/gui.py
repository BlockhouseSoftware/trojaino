from __future__ import annotations

import json
import re
import threading
import webbrowser
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from trojaino.contributions import (
    ContributionError,
    OFFICIAL_CONTRIBUTION_ENDPOINT,
    build_contribution_payload,
    contribution_preview,
    submit_contribution,
)
from trojaino.file_utils import estimate_project
from trojaino.report import render_html, render_json
from trojaino.scanner import BUDGET_PRESETS, annotate_result, scan_path


DEFAULT_REPORT_DIRNAME = "TrojainoReports"


def default_output_dir(target: Path) -> Path:
    """Keep reports beside the artifact, outside a containing Git repository."""
    selected = Path(target).expanduser().absolute()
    artifact_dir = selected if selected.is_dir() else selected.parent
    for candidate in (artifact_dir, *artifact_dir.parents):
        if (candidate / ".git").exists():
            return candidate.parent / DEFAULT_REPORT_DIRNAME
    return artifact_dir / DEFAULT_REPORT_DIRNAME


def _safe_target_name(target: Path) -> str:
    name = Path(target).expanduser().name or "scan"
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
    return normalized or "scan"


def report_paths(
    target: Path,
    output_dir: Path,
    *,
    moment: datetime | None = None,
) -> tuple[Path, Path]:
    """Return a collision-free HTML/JSON pair for one selected artifact."""
    timestamp = (moment or datetime.now(timezone.utc)).strftime("%Y%m%d-%H%M%S")
    stem = f"{_safe_target_name(target)}-{timestamp}"
    output = Path(output_dir).expanduser()
    suffix = 1
    while True:
        label = stem if suffix == 1 else f"{stem}-{suffix}"
        html_path = output / f"{label}.html"
        json_path = output / f"{label}.json"
        if not html_path.exists() and not json_path.exists():
            return html_path, json_path
        suffix += 1


def run_scan(target: Path, *, profile: str, budget_name: str):
    """Run the shared scanner with the same bounded preset used by the CLI."""
    selected = Path(target).expanduser().absolute()
    limits = BUDGET_PRESETS[budget_name]
    estimate = estimate_project(selected, profile=profile)
    result = scan_path(selected, profile=profile, limits=limits)
    return annotate_result(
        result,
        preflight=estimate,
        limits=limits,
        budget_name=budget_name,
        recommended_command=None,
    )


def write_reports(result, *, html_path: Path | None, json_path: Path | None) -> None:
    """Write only reports the user explicitly selected in the GUI."""
    for path, content in (
        (html_path, render_html(result) if html_path else None),
        (json_path, render_json(result) if json_path else None),
    ):
        if path is None or content is None:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")


def _format_bytes(value: int) -> str:
    if value < 1_000:
        return f"{value} bytes"
    if value < 1_000_000:
        return f"{value / 1_000:.1f} KB"
    return f"{value / 1_000_000:.1f} MB"


def _preset_summary(name: str) -> str:
    limits = BUDGET_PRESETS[name]
    return (
        f"{name.title()}: up to {limits.max_elapsed_seconds:g} seconds, "
        f"{limits.max_files:,} text files, {_format_bytes(limits.max_total_bytes)} total text."
    )


class TrojainoGui:
    def __init__(
        self,
        root,
        *,
        open_report: Callable[[str], bool] = webbrowser.open,
    ):
        import tkinter as tk
        from tkinter import filedialog, messagebox, ttk

        self.tk = tk
        self.filedialog = filedialog
        self.messagebox = messagebox
        self.ttk = ttk
        self.root = root
        self.open_report = open_report

        self.running = False
        self.last_html_path: Path | None = None
        self.last_result = None

        root.title("Trojaino")
        root.minsize(720, 520)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        self.target_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.profile_var = tk.StringVar(value="default")
        self.budget_var = tk.StringVar(value="standard")
        self.html_var = tk.BooleanVar(value=True)
        self.json_var = tk.BooleanVar(value=True)
        self.open_var = tk.BooleanVar(value=True)
        self.status_var = tk.StringVar(value="Choose a project or file to scan. Trojaino never runs the selected code.")
        self.summary_var = tk.StringVar(value=_preset_summary("standard"))

        frame = ttk.Frame(root, padding=18)
        frame.grid(sticky="nsew")
        frame.columnconfigure(1, weight=1)
        frame.rowconfigure(7, weight=1)

        ttk.Label(frame, text="Trojaino", font=("TkDefaultFont", 20, "bold")).grid(row=0, column=0, columnspan=3, sticky="w")
        ttk.Label(
            frame,
            text="Local, deterministic evidence before installation. A result is never a certification of safety.",
            wraplength=640,
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 16))

        ttk.Label(frame, text="Project or file").grid(row=2, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.target_var).grid(row=2, column=1, sticky="ew", padx=8)
        target_buttons = ttk.Frame(frame)
        target_buttons.grid(row=2, column=2)
        ttk.Button(target_buttons, text="Folder…", command=self.choose_folder).grid(row=0, column=0)
        ttk.Button(target_buttons, text="File…", command=self.choose_file).grid(row=0, column=1, padx=(6, 0))

        ttk.Label(frame, text="Scan profile").grid(row=3, column=0, sticky="w", pady=(14, 0))
        profile_frame = ttk.Frame(frame)
        profile_frame.grid(row=3, column=1, columnspan=2, sticky="w", padx=8, pady=(14, 0))
        ttk.Radiobutton(profile_frame, text="Standard", variable=self.profile_var, value="default").grid(row=0, column=0, padx=(0, 14))
        ttk.Radiobutton(profile_frame, text="Release (skip tests, docs, examples)", variable=self.profile_var, value="release").grid(row=0, column=1)

        ttk.Label(frame, text="Resource limit").grid(row=4, column=0, sticky="w", pady=(14, 0))
        budget_frame = ttk.Frame(frame)
        budget_frame.grid(row=4, column=1, columnspan=2, sticky="w", padx=8, pady=(14, 0))
        for index, name in enumerate(BUDGET_PRESETS):
            ttk.Radiobutton(
                budget_frame,
                text=name.title(),
                variable=self.budget_var,
                value=name,
                command=self.refresh_budget_summary,
            ).grid(row=0, column=index, padx=(0, 14))
        ttk.Label(frame, textvariable=self.summary_var, wraplength=560).grid(row=5, column=1, columnspan=2, sticky="w", padx=8, pady=(3, 0))

        ttk.Separator(frame).grid(row=6, column=0, columnspan=3, sticky="ew", pady=16)

        output_frame = ttk.LabelFrame(frame, text="Reports", padding=12)
        output_frame.grid(row=7, column=0, columnspan=3, sticky="nsew")
        output_frame.columnconfigure(1, weight=1)
        ttk.Checkbutton(output_frame, text="Save HTML report", variable=self.html_var, command=self.refresh_controls).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(output_frame, text="Save JSON report", variable=self.json_var, command=self.refresh_controls).grid(row=0, column=1, sticky="w")
        ttk.Label(output_frame, text="Suggested report folder:").grid(row=1, column=0, sticky="w", pady=(12, 0))
        self.output_entry = ttk.Entry(output_frame, textvariable=self.output_var)
        self.output_entry.grid(row=1, column=1, sticky="ew", padx=8, pady=(12, 0))
        self.output_button = ttk.Button(output_frame, text="Choose…", command=self.choose_output)
        self.output_button.grid(row=1, column=2, pady=(12, 0))
        self.open_check = ttk.Checkbutton(output_frame, text="Open HTML report when finished", variable=self.open_var)
        self.open_check.grid(row=2, column=0, columnspan=3, sticky="w", pady=(8, 0))

        self.status_label = ttk.Label(frame, textvariable=self.status_var, wraplength=660)
        self.status_label.grid(row=8, column=0, columnspan=3, sticky="w", pady=(16, 8))
        controls = ttk.Frame(frame)
        controls.grid(row=9, column=0, columnspan=3, sticky="e")
        self.scan_button = ttk.Button(controls, text="Scan selected project", command=self.start_scan)
        self.scan_button.grid(row=0, column=0)
        self.open_button = ttk.Button(controls, text="Open latest HTML report", command=self.open_latest, state="disabled")
        self.open_button.grid(row=0, column=1, padx=(8, 0))
        self.share_button = ttk.Button(controls, text="Share anonymous statistics…", command=self.preview_contribution, state="disabled")
        self.share_button.grid(row=0, column=2, padx=(8, 0))
        self.refresh_controls()

    def choose_folder(self) -> None:
        selected = self.filedialog.askdirectory(title="Choose project folder to scan", mustexist=True)
        if not selected:
            return
        self.set_target(Path(selected))

    def choose_file(self) -> None:
        selected = self.filedialog.askopenfilename(title="Choose file to scan")
        if selected:
            self.set_target(Path(selected))

    def set_target(self, target: Path) -> None:
        self.target_var.set(str(target))
        self.output_var.set(str(default_output_dir(target)))

    def choose_output(self) -> None:
        selected = self.filedialog.askdirectory(title="Choose report folder", mustexist=True)
        if selected:
            self.output_var.set(selected)

    def refresh_budget_summary(self) -> None:
        self.summary_var.set(_preset_summary(self.budget_var.get()))

    def refresh_controls(self) -> None:
        reports_selected = self.html_var.get() or self.json_var.get()
        state = "normal" if reports_selected and not self.running else "disabled"
        self.output_entry.configure(state=state)
        self.output_button.configure(state=state)
        self.open_check.configure(state="normal" if self.html_var.get() and not self.running else "disabled")

    def start_scan(self) -> None:
        if self.running:
            return
        target_text = self.target_var.get().strip()
        if not target_text:
            self.messagebox.showerror("Choose a project", "Choose a file or project folder before scanning.")
            return
        target = Path(target_text).expanduser()
        if not target.exists():
            self.messagebox.showerror("Project not found", f"Trojaino could not find:\n{target}")
            return
        if not self.html_var.get() and not self.json_var.get():
            self.messagebox.showerror("Choose a report", "Choose HTML, JSON, or both report formats.")
            return
        output_text = self.output_var.get().strip()
        if not output_text:
            self.messagebox.showerror("Choose a report folder", "Choose where Trojaino should save the report.")
            return

        output = Path(output_text).expanduser()
        self.running = True
        self.scan_button.configure(state="disabled")
        self.open_button.configure(state="disabled")
        self.share_button.configure(state="disabled")
        self.refresh_controls()
        self.status_var.set(f"Scanning with the bounded {self.budget_var.get()} preset. The selected code is not executed.")
        thread = threading.Thread(
            target=self._scan_worker,
            args=(target, output, self.profile_var.get(), self.budget_var.get(), self.html_var.get(), self.json_var.get(), self.open_var.get()),
            daemon=True,
        )
        thread.start()

    def _scan_worker(self, target: Path, output: Path, profile: str, budget: str, save_html: bool, save_json: bool, open_html: bool) -> None:
        try:
            result = run_scan(target, profile=profile, budget_name=budget)
            html_path, json_path = report_paths(target, output)
            write_reports(
                result,
                html_path=html_path if save_html else None,
                json_path=json_path if save_json else None,
            )
            self.root.after(0, lambda: self.finish_scan(result, html_path if save_html else None, json_path if save_json else None, open_html))
        except Exception as exc:
            self.root.after(0, lambda: self.fail_scan(type(exc).__name__))

    def finish_scan(self, result, html_path: Path | None, json_path: Path | None, open_html: bool) -> None:
        self.running = False
        self.scan_button.configure(state="normal")
        self.refresh_controls()
        self.last_html_path = html_path
        self.last_result = result
        if html_path:
            self.open_button.configure(state="normal")
        self.share_button.configure(state="normal")
        locations = ", ".join(str(path) for path in (html_path, json_path) if path)
        coverage = "complete" if result.complete else "incomplete"
        self.status_var.set(f"{result.verdict} · Scan {coverage}. Report saved: {locations}")
        if html_path and open_html:
            self.open_report(html_path.resolve().as_uri())

    def fail_scan(self, error_name: str) -> None:
        self.running = False
        self.scan_button.configure(state="normal")
        self.refresh_controls()
        self.status_var.set("The scan could not finish. No safety conclusion is available.")
        self.messagebox.showerror("Scan could not finish", f"Trojaino stopped safely ({error_name}). No report was written.")

    def open_latest(self) -> None:
        if self.last_html_path and self.last_html_path.exists():
            self.open_report(self.last_html_path.resolve().as_uri())

    def preview_contribution(self) -> None:
        if self.last_result is None:
            return
        try:
            payload = build_contribution_payload(self.last_result)
            preview = contribution_preview(payload)
        except ContributionError as exc:
            self.messagebox.showerror("Could not prepare anonymous statistics", str(exc))
            return

        dialog = self.tk.Toplevel(self.root)
        dialog.title("Share anonymous scan statistics")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.minsize(720, 440)
        dialog.columnconfigure(0, weight=1)
        dialog.rowconfigure(2, weight=1)
        self.ttk.Label(dialog, text="Help improve Trojaino — optional and off by default", font=("TkDefaultFont", 14, "bold")).grid(row=0, column=0, sticky="w", padx=16, pady=(16, 4))
        self.ttk.Label(
            dialog,
            text=(
                "This sends only the exact aggregate JSON below: scanner version, verdict, scan-size band, "
                "rule/category counts, and scan issue counts. It never sends code, report files, paths, "
                "filenames, line numbers, evidence, credentials, or the selected target."
            ),
            wraplength=680,
        ).grid(row=1, column=0, sticky="w", padx=16, pady=(0, 10))
        text = self.tk.Text(dialog, height=18, wrap="word")
        text.grid(row=2, column=0, sticky="nsew", padx=16)
        text.insert("1.0", preview)
        text.configure(state="disabled")
        controls = self.ttk.Frame(dialog)
        controls.grid(row=3, column=0, sticky="e", padx=16, pady=16)
        self.ttk.Button(controls, text="Close", command=dialog.destroy).grid(row=0, column=0)
        if OFFICIAL_CONTRIBUTION_ENDPOINT:
            self.ttk.Button(
                controls,
                text="Send anonymous statistics",
                command=lambda: self.send_contribution(dialog, payload),
            ).grid(row=0, column=1, padx=(8, 0))
        else:
            self.ttk.Label(
                controls,
                text="Sending is unavailable until an official Trojaino contribution service is configured.",
                wraplength=420,
            ).grid(row=1, column=0, columnspan=2, sticky="e", pady=(8, 0))

    def send_contribution(self, dialog, payload: dict) -> None:
        if not OFFICIAL_CONTRIBUTION_ENDPOINT:
            return
        try:
            receipt = submit_contribution(payload)
        except ContributionError as exc:
            self.messagebox.showerror("Anonymous statistics were not sent", str(exc), parent=dialog)
            return
        dialog.destroy()
        self.messagebox.showinfo(
            "Anonymous statistics sent",
            "Thank you. Save these values together; they are required to delete the contribution later.\n\n"
            f"Receipt: {receipt.receipt_id}\n"
            f"Deletion token: {receipt.deletion_token}",
        )


def launch_gui() -> int:
    """Launch the optional native GUI without making Tk a CLI import dependency."""
    try:
        import tkinter as tk
    except ImportError:
        print("Trojaino GUI is unavailable because this Python installation does not include Tkinter. Use `trojaino scan …` or install Python with Tk support.")
        return 1
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"Trojaino GUI needs a graphical desktop session: {exc}")
        return 1
    TrojainoGui(root)
    root.mainloop()
    return 0
