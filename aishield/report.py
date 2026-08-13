from __future__ import annotations

import html
import json
import unicodedata

from aishield import __version__
from aishield.models import ScanResult


_BIDI_CONTROLS = {
    "\u061c", "\u200e", "\u200f", "\u202a", "\u202b", "\u202c", "\u202d", "\u202e",
    "\u2066", "\u2067", "\u2068", "\u2069",
}


def sanitize_human(value: object) -> str:
    """Make untrusted fields single-line and inert in terminals/browsers."""
    output = []
    for char in str(value):
        code = ord(char)
        if char in {"\r", "\n", "\t"}:
            output.append(" ")
        elif char in {"\u2028", "\u2029"}:
            output.append(f"\\u{code:04x}")
        elif char in _BIDI_CONTROLS or code < 32 or 0x7F <= code <= 0x9F or unicodedata.category(char) == "Cf":
            output.append(f"\\u{code:04x}")
        else:
            output.append(char)
    return "".join(output)


def _html(value: object) -> str:
    return html.escape(sanitize_human(value))


def render_text(result: ScanResult, max_findings: int | None = 5) -> str:
    lines = [
        f"Trojaino v{__version__}",
        "",
        f"Target: {sanitize_human(result.target)}",
        f"Profile: {sanitize_human(result.profile)}",
        f"Verdict: {result.verdict}",
        f"Coverage: {result.files_scanned} files scanned · {result.unreadable_files} unreadable",
        "",
    ]
    if result.preflight:
        estimate = result.preflight
        budget_name = (result.budget or {}).get("preset", "custom")
        lines.extend([
            f"Preflight estimate: {estimate.eligible_files} eligible files · {estimate.total_bytes} bytes · "
            f"{estimate.symlinks} symlinks · {estimate.unreadable_entries} unreadable entries",
            f"Budget: {sanitize_human(budget_name)}",
        ])
        if result.recommended_command:
            lines.append(f"Suggested higher-budget command: {sanitize_human(result.recommended_command)}")
        lines.append("")
    if not result.complete:
        lines.append("INCOMPLETE SCAN: coverage limits or input errors prevented a clean assessment.")
        for issue in result.issues or []:
            location = f" ({sanitize_human(issue.file)})" if issue.file else ""
            lines.append(f"- {sanitize_human(issue.code)}{location}: {sanitize_human(issue.message)}")
        lines.append("")
    if result.capabilities:
        lines.append("Detected runtime capabilities (review signals, not verdict inputs):")
        for capability in result.capabilities:
            loc = capability.file if capability.line is None else f"{capability.file}:{capability.line}"
            lines.append(f"- {sanitize_human(capability.title)}: {sanitize_human(loc)} ({sanitize_human(capability.rule)})")
        lines.append("")
    if not result.findings and not result.complete:
        lines.append("No risk-free conclusion is available because the scan is incomplete.")
        return "\n".join(lines)
    if not result.findings:
        lines.extend([
            f"No critical risks found by deterministic v{__version__} rules.",
            "This is not a guarantee of safety. Use --deep in future versions for model-assisted review.",
        ])
        return "\n".join(lines)
    shown_findings = result.findings if max_findings is None else result.findings[:max_findings]
    heading = "All risks:" if max_findings is None else f"Top {len(shown_findings)} risks:"
    lines.append(heading)
    for index, finding in enumerate(shown_findings, start=1):
        loc = finding.file if finding.line is None else f"{finding.file}:{finding.line}"
        lines.extend([
            f"{index}. [{finding.severity.upper()} / {finding.confidence} confidence / {finding.disposition}] {sanitize_human(finding.title)}",
            f"   {sanitize_human(loc)}",
            f"   Context: {sanitize_human(finding.context)}",
            f"   Evidence: {sanitize_human(finding.evidence)}",
            f"   Why: {sanitize_human(finding.why_it_matters)}",
            f"   Fix: {sanitize_human(finding.recommendation)}",
            "",
        ])
    if max_findings is not None and len(result.findings) > max_findings:
        omitted = len(result.findings) - max_findings
        lines.append(f"... {omitted} additional findings omitted from terminal output. Use --all or --json for full output.")
    if result.verdict == "DO NOT RUN":
        lines.append("Recommended next step: Do not run install commands or deploy until critical/high findings are fixed or explicitly dispositioned.")
    elif result.verdict == "CAUTION":
        lines.append("Recommended next step: Review and fix the listed findings before giving this artifact secrets or customer data.")
    else:
        lines.append("Recommended next step: No critical risks found by deterministic rules; still review before production use.")
    return "\n".join(lines)


def render_json(result: ScanResult) -> str:
    return json.dumps(result.to_dict(), indent=2, sort_keys=True, ensure_ascii=True)


def _severity_counts(result: ScanResult) -> dict[str, int]:
    return {
        severity: sum(1 for finding in result.findings if finding.severity == severity)
        for severity in ("critical", "high", "medium", "low")
    }


def render_html(result: ScanResult) -> str:
    counts = _severity_counts(result)
    total_findings = len(result.findings)
    verdict_class = {
        "DO NOT RUN": "verdict-stop",
        "CAUTION": "verdict-caution",
        "NO CRITICAL RISKS FOUND": "verdict-clear",
    }[result.verdict]
    summary_cards = "\n".join(
        f"""
        <div class="summary-card severity-{_html(severity)}">
          <span class="count">{count}</span>
          <span>{_html(severity.title())}</span>
        </div>"""
        for severity, count in counts.items()
    )
    rows = []
    for finding in result.findings:
        loc = finding.file if finding.line is None else f"{finding.file}:{finding.line}"
        rows.append(f"""
        <article class="finding severity-{_html(finding.severity)} disposition-{_html(finding.disposition)}">
          <div class="finding-kicker">{_html(finding.severity)} risk · {_html(finding.confidence)} confidence</div>
          <h2>{_html(finding.title)}</h2>
          <p class="meta">{_html(loc)}</p>
          <p class="labels"><span>{_html(finding.disposition.replace("_", " "))}</span><span>Context: {_html(finding.context.replace("_", " "))}</span></p>
          <div class="finding-detail"><strong>Evidence</strong><code>{_html(finding.evidence)}</code></div>
          <p><strong>Why it matters</strong><br>{_html(finding.why_it_matters)}</p>
          <p><strong>Recommended action</strong><br>{_html(finding.recommendation)}</p>
        </article>""")
    if rows:
        body = "\n".join(rows)
    elif result.complete:
        body = f'<section class="empty-state"><p class="eyebrow">Release signal</p><h2>No critical risks found</h2><p>No findings were produced by the deterministic v{__version__} rules. This is useful evidence, not a safety certification.</p></section>'
    else:
        body = '<section class="empty-state"><p class="eyebrow">Coverage warning</p><h2>Scan incomplete</h2><p>No risk-free conclusion is available because coverage limits or input errors prevented a complete scan.</p></section>'
    incomplete_panel = ""
    if not result.complete:
        issue_rows = "".join(
            f"<li><strong>{_html(issue.code)}</strong><span>{_html(issue.file or 'scan')}</span><p>{_html(issue.message)}</p></li>"
            for issue in result.issues or []
        )
        incomplete_panel = f"""
  <section aria-label="Incomplete scan details" class="section-card">
    <p class="eyebrow">Coverage warning</p>
    <h2>Incomplete scan — do not treat this as a clean result.</h2>
    <ul class="capability-list">{issue_rows}</ul>
  </section>"""
    capability_rows = "\n".join(
        f"<li><strong>{_html(capability.title)}</strong><span>{_html(capability.file if capability.line is None else f'{capability.file}:{capability.line}')} · <code>{_html(capability.rule)}</code></span><code>{_html(capability.evidence)}</code></li>"
        for capability in result.capabilities or []
    ) or '<li class="empty-capability">No proven MCP runtime capabilities detected.</li>'
    preflight_panel = ""
    if result.preflight:
        estimate = result.preflight
        budget_name = (result.budget or {}).get("preset", "custom")
        recommendation = (
            f"<p><strong>Suggested higher-budget rerun:</strong> <code>{_html(result.recommended_command)}</code></p>"
            if result.recommended_command else ""
        )
        preflight_panel = f"""
  <section aria-label="Preflight estimate" class="section-card">
    <p class="eyebrow">Bounded preflight</p>
    <h2>Estimated scan scope</h2>
    <p>{estimate.eligible_files} eligible files · {_html(estimate.total_bytes)} bytes · {estimate.symlinks} symlinks · {estimate.unreadable_entries} unreadable entries · budget {_html(budget_name)}</p>
    {recommendation}
  </section>"""
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="theme-color" content="#07090c">
  <title>Trojaino · Pre-install Report</title>
  <style>
    :root {{ --bg:#07090c; --panel:#0f141b; --panel-deep:#0a0e13; --line:#1d242e; --line-soft:#161c24; --text:#e8edf4; --muted:#96a2b3; --dim:#6b7789; --accent:#00e5a0; --accent-dim:#00b47e; --warn:#ffb340; --danger:#ff5f5f; --danger-soft:rgba(255,95,95,.10); --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,"Liberation Mono",monospace; --sans:-apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,Helvetica,Arial,sans-serif; --shadow:0 24px 60px -30px rgba(0,0,0,.9); }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; color:var(--text); font-family:var(--sans); line-height:1.6; background:var(--bg); -webkit-font-smoothing:antialiased; }}
    body::before {{ content:""; position:fixed; inset:0; z-index:-1; pointer-events:none; background:radial-gradient(900px 500px at 50% -8%,rgba(0,229,160,.10),transparent 62%),radial-gradient(700px 420px at 92% 6%,rgba(0,140,255,.07),transparent 60%); }}
    main {{ width:min(1080px,calc(100% - 40px)); margin:0 auto; padding:28px 0 60px; }}
    .report-topline {{ display:flex; justify-content:space-between; align-items:center; gap:16px; margin:0 0 18px; color:var(--accent); font:600 12px var(--mono); letter-spacing:.12em; text-transform:uppercase; }}
    .report-topline span:last-child {{ color:var(--dim); letter-spacing:.08em; }}
    header {{ display:grid; grid-template-columns:minmax(0,1.25fr) minmax(240px,.75fr); gap:28px; align-items:end; padding:clamp(28px,5vw,54px); border:1px solid var(--line); border-radius:16px; background:linear-gradient(145deg,#0d1219,#080b0f); box-shadow:var(--shadow); }}
    .eyebrow {{ margin:0 0 9px; color:var(--accent-dim); font:600 12px var(--mono); letter-spacing:.14em; text-transform:uppercase; }}
    h1,h2 {{ letter-spacing:-.03em; }}
    h1 {{ max-width:660px; margin:0; font-size:clamp(38px,6vw,66px); line-height:1.06; }}
    .target {{ max-width:670px; margin:18px 0 0; color:var(--muted); overflow-wrap:anywhere; }}
    .target strong,.finding strong {{ color:var(--text); }}
    .verdict-panel {{ padding:22px; border:1px solid var(--line); border-radius:12px; background:var(--panel-deep); }}
    .verdict-label {{ display:block; margin-bottom:8px; color:var(--dim); font:600 11px var(--mono); letter-spacing:.12em; text-transform:uppercase; }}
    .verdict {{ display:inline-block; padding:8px 11px; border-radius:8px; font:650 12px var(--mono); letter-spacing:.05em; }}
    .verdict-clear {{ background:rgba(0,229,160,.09); color:var(--accent); border:1px solid rgba(0,229,160,.28); }}
    .verdict-caution {{ background:rgba(255,179,64,.10); color:var(--warn); border:1px solid rgba(255,179,64,.32); }}
    .verdict-stop {{ background:var(--danger-soft); color:var(--danger); border:1px solid rgba(255,95,95,.34); }}
    .coverage {{ margin:14px 0 0; color:var(--muted); font-size:14px; }}
    .summary {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:18px 0; }}
    .summary-card {{ padding:18px 20px; border:1px solid var(--line); border-radius:12px; background:var(--panel); }}
    .summary-card .count {{ display:block; color:var(--accent); font:700 36px var(--mono); line-height:1; }}
    .summary-card span:last-child {{ display:block; margin-top:8px; color:var(--dim); font:600 11px var(--mono); letter-spacing:.11em; text-transform:uppercase; }}
    .summary-card.severity-critical .count {{ color:var(--danger); }} .summary-card.severity-high .count {{ color:#ff8b72; }} .summary-card.severity-medium .count {{ color:var(--warn); }}
    .section-card {{ margin:18px 0; padding:28px; border:1px solid var(--line); border-radius:12px; background:var(--panel); }}
    .section-card h2 {{ margin:0 0 8px; font-size:28px; }} .section-card p {{ margin:0; color:var(--muted); }}
    .capability-list {{ display:grid; gap:10px; margin:18px 0 0; padding:0; list-style:none; }}
    .capability-list li {{ display:grid; gap:3px; padding:14px 16px; border:1px solid var(--line-soft); border-radius:10px; background:var(--panel-deep); }}
    .capability-list strong {{ color:var(--text); }} .capability-list span {{ color:var(--muted); font-size:13px; overflow-wrap:anywhere; }} .capability-list code {{ width:max-content; max-width:100%; overflow-wrap:anywhere; }} .empty-capability {{ color:var(--dim); font-style:italic; }}
    .finding {{ margin:18px 0; padding:28px; border:1px solid var(--line); border-left:5px solid var(--dim); border-radius:12px; background:var(--panel); }}
    .finding.severity-critical {{ border-left-color:var(--danger); }} .finding.severity-high {{ border-left-color:#ff8b72; }} .finding.severity-medium {{ border-left-color:var(--warn); }}
    .finding-kicker {{ color:var(--accent-dim); font:600 11px var(--mono); letter-spacing:.12em; text-transform:uppercase; }}
    .finding h2 {{ margin:7px 0 5px; font-size:27px; line-height:1.1; }} .finding p {{ color:var(--muted); }} .meta {{ margin:0; color:var(--dim)!important; font:14px var(--mono); overflow-wrap:anywhere; }}
    .labels {{ display:flex; flex-wrap:wrap; gap:8px; margin:15px 0; }} .labels span {{ padding:5px 9px; border:1px solid var(--line); border-radius:999px; background:var(--panel-deep); color:var(--muted); font:600 11px var(--mono); text-transform:capitalize; }}
    .finding-detail {{ display:grid; gap:7px; margin:16px 0; }} code {{ padding:3px 6px; border-radius:6px; background:#080c10; color:#b9f8df; font-family:var(--mono); font-size:.88em; overflow-wrap:anywhere; }}
    .empty-state {{ margin:18px 0; padding:clamp(30px,6vw,60px); border:1px solid var(--line); border-radius:16px; background:linear-gradient(145deg,#0d1219,#080b0f); }} .empty-state h2 {{ margin:0 0 8px; font-size:38px; }} .empty-state p:last-child {{ max-width:620px; color:var(--muted); }}
    footer {{ display:flex; justify-content:space-between; gap:16px; margin:30px 4px 0; color:var(--dim); font-size:13px; }} footer strong {{ color:var(--text); }}
    @media (max-width:720px) {{ main {{ width:min(100% - 28px,1080px); padding-top:18px; }} header {{ grid-template-columns:1fr; padding:28px; }} .summary {{ grid-template-columns:repeat(2,1fr); }} .section-card,.finding {{ padding:22px; }} footer {{ display:block; }} footer p + p {{ margin-top:8px; }} }}
  </style>
</head>
<body>
<main>
  <div class="report-topline"><span>Trojaino</span><span>Local pre-install report · v{__version__} alpha</span></div>
  <header>
    <div>
      <p class="eyebrow">Local deterministic scan record</p>
      <h1>Know what it does<br>before it runs.</h1>
      <p class="target"><strong>Target:</strong> {_html(result.target)}<br><strong>Profile:</strong> {_html(result.profile)}</p>
    </div>
    <aside class="verdict-panel">
      <span class="verdict-label">Assessment</span>
      <span class="verdict {verdict_class}">{_html(result.verdict)}</span>
      <p class="coverage">{_html('Complete' if result.complete else 'Incomplete')} · {total_findings} findings · {result.files_scanned} files scanned · {result.unreadable_files} unreadable</p>
    </aside>
  </header>
  {preflight_panel}
  {incomplete_panel}
  <section aria-label="Finding summary" class="summary">{summary_cards}</section>
  <section class="section-card">
    <p class="eyebrow">How to read this</p>
    <h2>Evidence before execution.</h2>
    <p>Findings are ordered with <em>actionable</em> items first. <em>Review</em> needs human judgment; test/example and documentation context remain visible but do not independently make an artifact unsafe. Trojaino is a deterministic alpha scanner, not a safety certification.</p>
  </section>
  <section aria-label="Runtime capability summary" class="section-card">
    <p class="eyebrow">Capability summary</p>
    <h2>Runtime surface</h2>
    <p>Capabilities are informed-review signals. They do not independently change this report's verdict; inspect their supporting evidence alongside actionable findings.</p>
    <ul class="capability-list">{capability_rows}</ul>
  </section>
  {body}
  <footer>
    <p><strong>Trojaino</strong> · Local deterministic pre-install scanning</p>
    <p>Review evidence before running install commands, giving the project secrets, or deploying it.</p>
  </footer>
</main>
</body>
</html>"""
