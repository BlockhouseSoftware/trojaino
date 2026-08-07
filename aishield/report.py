from __future__ import annotations

import html
import json
from aishield.models import ScanResult


def render_text(result: ScanResult, max_findings: int | None = 5) -> str:
    lines = [
        "AI Shield v0.1",
        "",
        f"Target: {result.target}",
        f"Profile: {result.profile}",
        f"Verdict: {result.verdict}",
        f"Coverage: {result.files_scanned} files scanned · {result.unreadable_files} unreadable",
        "",
    ]
    if result.capabilities:
        lines.append("Detected runtime capabilities (review signals, not verdict inputs):")
        for capability in result.capabilities:
            loc = capability.file if capability.line is None else f"{capability.file}:{capability.line}"
            lines.append(f"- {capability.title}: {loc} ({capability.rule})")
        lines.append("")
    if not result.findings:
        lines.extend([
            "No critical risks found by deterministic v0.1 rules.",
            "This is not a guarantee of safety. Use --deep in future versions for model-assisted review.",
        ])
        return "\n".join(lines)
    shown_findings = result.findings if max_findings is None else result.findings[:max_findings]
    heading = "All risks:" if max_findings is None else f"Top {len(shown_findings)} risks:"
    lines.append(heading)
    for index, finding in enumerate(shown_findings, start=1):
        loc = finding.file if finding.line is None else f"{finding.file}:{finding.line}"
        lines.extend([
            f"{index}. [{finding.severity.upper()} / {finding.confidence} confidence / {finding.disposition}] {finding.title}",
            f"   {loc}",
            f"   Context: {finding.context}",
            f"   Evidence: {finding.evidence}",
            f"   Why: {finding.why_it_matters}",
            f"   Fix: {finding.recommendation}",
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
    return json.dumps(result.to_dict(), indent=2, sort_keys=True)


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
        <div class="summary-card severity-{html.escape(severity)}">
          <span class="count">{count}</span>
          <span>{html.escape(severity.title())}</span>
        </div>"""
        for severity, count in counts.items()
    )
    rows = []
    for finding in result.findings:
        loc = finding.file if finding.line is None else f"{finding.file}:{finding.line}"
        rows.append(f"""
        <article class="finding severity-{html.escape(finding.severity)} disposition-{html.escape(finding.disposition)}">
          <div class="finding-kicker">{html.escape(finding.severity)} risk · {html.escape(finding.confidence)} confidence</div>
          <h2>{html.escape(finding.title)}</h2>
          <p class="meta">{html.escape(loc)}</p>
          <p class="labels"><span>{html.escape(finding.disposition.replace("_", " "))}</span><span>Context: {html.escape(finding.context.replace("_", " "))}</span></p>
          <div class="finding-detail"><strong>Evidence</strong><code>{html.escape(finding.evidence)}</code></div>
          <p><strong>Why it matters</strong><br>{html.escape(finding.why_it_matters)}</p>
          <p><strong>Recommended action</strong><br>{html.escape(finding.recommendation)}</p>
        </article>""")
    body = "\n".join(rows) or '<section class="empty-state"><p class="eyebrow">Release signal</p><h2>No critical risks found</h2><p>No findings were produced by the deterministic v0.1 rules. This is useful evidence, not a safety certification.</p></section>'
    capability_rows = "\n".join(
        f"<li><strong>{html.escape(capability.title)}</strong><span>{html.escape(capability.file if capability.line is None else f'{capability.file}:{capability.line}')} · <code>{html.escape(capability.rule)}</code></span><code>{html.escape(capability.evidence)}</code></li>"
        for capability in result.capabilities or []
    ) or '<li class="empty-capability">No proven MCP runtime capabilities detected.</li>'
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>AI Shield · Scan Report</title>
  <style>
    :root {{ --burgundy:#5A1E2D; --burgundy-deep:#421622; --beige:#C8B49A; --cream:#F7F6F4; --paper:#fffdf9; --charcoal:#222222; --muted:#6f6864; --line:#eadfd4; --soft:#f1e8df; --danger:#a3213d; --shadow:0 16px 36px rgba(72, 43, 32, .10); --shadow-soft:0 8px 22px rgba(72, 43, 32, .07); }}
    * {{ box-sizing: border-box; }}
    body {{ margin:0; color:var(--charcoal); font-family:-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; line-height:1.55; background:radial-gradient(circle at 86% 3%, rgba(200,180,154,.40), transparent 25rem), linear-gradient(180deg,#fffdf9 0%,var(--cream) 54%,#efe5dc 100%); }}
    main {{ width:min(1120px, calc(100% - 40px)); margin:0 auto; padding:28px 0 60px; }}
    .report-topline {{ display:flex; justify-content:space-between; align-items:center; gap:16px; margin:0 0 18px; color:var(--burgundy); font-size:12px; font-weight:900; letter-spacing:.14em; text-transform:uppercase; }}
    .report-topline span:last-child {{ color:var(--muted); letter-spacing:.08em; }}
    header {{ position:relative; overflow:hidden; display:grid; grid-template-columns:minmax(0,1.25fr) minmax(240px,.75fr); gap:28px; align-items:end; padding:clamp(28px,5vw,54px); border:1px solid rgba(90,30,45,.16); border-radius:32px; background:linear-gradient(135deg,#fffdf9 0%,#f3ebe3 53%,#eaded2 100%); box-shadow:var(--shadow); }}
    header::after {{ content:""; position:absolute; width:300px; height:300px; right:-145px; top:-165px; border-radius:50%; border:1px solid rgba(90,30,45,.12); box-shadow:0 0 0 28px rgba(90,30,45,.035), 0 0 0 56px rgba(90,30,45,.025); pointer-events:none; }}
    .eyebrow {{ margin:0 0 9px; color:var(--burgundy); font-size:12px; font-weight:900; letter-spacing:.15em; text-transform:uppercase; }}
    h1,h2 {{ font-family:Georgia, "Times New Roman", serif; letter-spacing:-.035em; }}
    h1 {{ max-width:660px; margin:0; color:var(--burgundy); font-size:clamp(38px,6vw,68px); line-height:.96; }}
    .target {{ max-width:670px; margin:18px 0 0; color:#514b48; overflow-wrap:anywhere; }}
    .target strong {{ color:var(--charcoal); }}
    .verdict-panel {{ position:relative; z-index:1; padding:22px; border:1px solid rgba(90,30,45,.15); border-radius:24px; background:rgba(255,253,249,.78); box-shadow:var(--shadow-soft); }}
    .verdict-label {{ display:block; margin-bottom:8px; color:var(--muted); font-size:11px; font-weight:900; letter-spacing:.12em; text-transform:uppercase; }}
    .verdict {{ display:inline-block; padding:8px 11px; border-radius:999px; font-size:12px; font-weight:900; letter-spacing:.05em; }}
    .verdict-clear {{ background:#e8f0e8; color:var(--burgundy); border:1px solid rgba(90,30,45,.18); }}
    .verdict-caution {{ background:#f6e8c5; color:#654d18; border:1px solid #d5bc75; }}
    .verdict-stop {{ background:#f5dfe3; color:var(--danger); border:1px solid #d99aa8; }}
    .coverage {{ margin:14px 0 0; color:#514b48; font-size:14px; }}
    .summary {{ display:grid; grid-template-columns:repeat(4,1fr); gap:12px; margin:18px 0; }}
    .summary-card {{ padding:18px 20px; border:1px solid var(--line); border-radius:22px; background:linear-gradient(145deg,var(--paper),#f5ece3); box-shadow:var(--shadow-soft); }}
    .summary-card .count {{ display:block; color:var(--burgundy); font-family:Georgia, "Times New Roman", serif; font-size:36px; font-weight:700; line-height:1; }}
    .summary-card span:last-child {{ display:block; margin-top:8px; color:var(--muted); font-size:11px; font-weight:900; letter-spacing:.11em; text-transform:uppercase; }}
    .summary-card.severity-critical .count {{ color:var(--danger); }}
    .summary-card.severity-high .count {{ color:#8c3d35; }}
    .summary-card.severity-medium .count {{ color:#80651c; }}
    .section-card {{ margin:18px 0; padding:28px; border:1px solid var(--line); border-radius:28px; background:rgba(255,253,249,.88); box-shadow:var(--shadow-soft); }}
    .section-card h2 {{ margin:0 0 8px; color:var(--burgundy); font-size:28px; }}
    .section-card p {{ margin:0; color:#514b48; }}
    .capability-list {{ display:grid; gap:10px; margin:18px 0 0; padding:0; list-style:none; }}
    .capability-list li {{ display:grid; gap:3px; padding:14px 16px; border:1px solid var(--line); border-radius:18px; background:var(--paper); }}
    .capability-list strong {{ color:var(--burgundy); }}
    .capability-list span {{ color:var(--muted); font-size:13px; overflow-wrap:anywhere; }}
    .capability-list code {{ width:max-content; max-width:100%; overflow-wrap:anywhere; }}
    .empty-capability {{ color:var(--muted); font-style:italic; }}
    .finding {{ margin:18px 0; padding:28px; border:1px solid var(--line); border-left:5px solid var(--beige); border-radius:26px; background:rgba(255,253,249,.94); box-shadow:var(--shadow-soft); }}
    .finding.severity-critical {{ border-left-color:var(--danger); }}
    .finding.severity-high {{ border-left-color:#a85a4c; }}
    .finding.severity-medium {{ border-left-color:#b39847; }}
    .finding-kicker {{ color:var(--burgundy); font-size:11px; font-weight:900; letter-spacing:.12em; text-transform:uppercase; }}
    .finding h2 {{ margin:7px 0 5px; color:var(--burgundy); font-size:27px; line-height:1.1; }}
    .finding p {{ color:#514b48; }}
    .finding strong {{ color:var(--charcoal); }}
    .meta {{ margin:0; color:var(--muted)!important; font-size:14px; overflow-wrap:anywhere; }}
    .labels {{ display:flex; flex-wrap:wrap; gap:8px; margin:15px 0; }}
    .labels span {{ padding:5px 9px; border:1px solid rgba(90,30,45,.15); border-radius:999px; background:var(--soft); color:var(--burgundy); font-size:11px; font-weight:850; text-transform:capitalize; }}
    .finding-detail {{ display:grid; gap:7px; margin:16px 0; }}
    code {{ padding:3px 6px; border-radius:6px; background:#f5eee7; color:var(--burgundy-deep); font-family:"SFMono-Regular", Consolas, monospace; font-size:.88em; overflow-wrap:anywhere; }}
    .empty-state {{ margin:18px 0; padding:clamp(30px,6vw,60px); border:1px solid rgba(90,30,45,.16); border-radius:30px; background:linear-gradient(145deg,var(--paper),#f2e7dc); box-shadow:var(--shadow-soft); }}
    .empty-state h2 {{ margin:0 0 8px; color:var(--burgundy); font-size:38px; }}
    .empty-state p:last-child {{ max-width:620px; color:#514b48; }}
    footer {{ display:flex; justify-content:space-between; gap:16px; margin:30px 4px 0; color:var(--muted); font-size:13px; }}
    footer strong {{ color:var(--burgundy); }}
    @media (max-width:720px) {{ main {{ width:min(100% - 28px,1120px); padding-top:18px; }} header {{ grid-template-columns:1fr; padding:28px; border-radius:26px; }} .summary {{ grid-template-columns:repeat(2,1fr); }} .section-card,.finding {{ padding:22px; border-radius:22px; }} footer {{ display:block; }} footer p + p {{ margin-top:8px; }} }}
  </style>
</head>
<body>
<main>
  <div class="report-topline"><span>AI Shield</span><span>Local pre-flight report · v0.1 alpha</span></div>
  <header>
    <div>
      <p class="eyebrow">Deterministic scan record</p>
      <h1>Clear evidence.<br>Better decisions.</h1>
      <p class="target"><strong>Target:</strong> {html.escape(result.target)}<br><strong>Profile:</strong> {html.escape(result.profile)}</p>
    </div>
    <aside class="verdict-panel">
      <span class="verdict-label">Assessment</span>
      <span class="verdict {verdict_class}">{html.escape(result.verdict)}</span>
      <p class="coverage">{total_findings} findings · {result.files_scanned} files scanned · {result.unreadable_files} unreadable</p>
    </aside>
  </header>
  <section aria-label="Finding summary" class="summary">{summary_cards}</section>
  <section class="section-card">
    <p class="eyebrow">How to read this</p>
    <h2>Evidence before certainty.</h2>
    <p>Findings are ordered with <em>actionable</em> items first. <em>Review</em> needs human judgment; test/example and documentation context remain visible but do not independently make an artifact unsafe. AI Shield is a deterministic alpha scanner, not a safety certification.</p>
  </section>
  <section aria-label="Runtime capability summary" class="section-card">
    <p class="eyebrow">Capability summary</p>
    <h2>Runtime surface</h2>
    <p>Capabilities are informed-review signals. They do not independently change this report's verdict; inspect their supporting evidence alongside actionable findings.</p>
    <ul class="capability-list">{capability_rows}</ul>
  </section>
  {body}
  <footer>
    <p><strong>AI Shield</strong> · Local deterministic pre-flight scanning</p>
    <p>Review evidence before running install commands, giving the project secrets, or deploying it.</p>
  </footer>
</main>
</body>
</html>"""
