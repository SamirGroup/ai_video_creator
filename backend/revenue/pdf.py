"""Revenue-share statement PDF (FR-69). Reuses `contracts.pdf.render_text_pdf`
(a dependency-free PDF writer) rather than pulling in reportlab/weasyprint.
"""
from __future__ import annotations

from contracts.pdf import render_text_pdf


def render_statement_pdf(statement) -> bytes:
    title = f"Revenue Share Statement — {statement.period_start.isoformat()} to {statement.period_end.isoformat()}"
    lines = [
        f"Creator: {statement.user.email}",
        f"Contract version: {statement.contract.contract_version.version}",
        f"Status: {statement.status}",
        "",
        f"Gross revenue (platform-generated videos): {statement.gross_revenue} {statement.currency}",
        f"Platform share ({statement.platform_share_pct}%): {statement.platform_share_amount} {statement.currency}",
        f"Creator share: {statement.creator_share_amount} {statement.currency}",
        f"Videos included: {statement.video_count}",
        "",
        "Per-video breakdown:",
    ]
    breakdown = statement.breakdown or {}
    if breakdown:
        for job_id, amount in sorted(breakdown.items()):
            lines.append(f"  - {job_id}: {amount} {statement.currency}")
    else:
        lines.append("  (none)")
    lines += [
        "",
        f"Finalized: {statement.finalized_at.isoformat() if statement.finalized_at else '-'}",
        "This statement reflects only revenue from videos generated and published",
        "by the platform on your behalf (FR-65). Your own pre-existing content is",
        "not included. You may dispute this statement within 14 days of finalization.",
    ]
    return render_text_pdf(title, lines, metadata={"Subject": "Revenue Share Statement", "Author": "AI YouTube Content Ecosystem"})
