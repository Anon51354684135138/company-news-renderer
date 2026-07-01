"""Plain-text painting backend for the PubCo Brief — the GUARANTEED-readable
backend. Added 2026-06-16.

Why this is the primary deliverable: binary files (.docx, .pdf) are uploaded to
Google Drive as a base64 blob emitted into a tool call, and that emit
intermittently scrambles bytes — which destroys the file (a corrupt ZIP/PDF is
unopenable). Confirmed repeatedly (incl. a hand emit). Plain TEXT has no such
failure mode: it is uploaded via `textContent` (not base64) and converts to a
Google Doc (`text/plain` → `application/vnd.google-apps.document`), so a stray
character is at worst a typo, never an unopenable file. The Google Doc reads
natively in Drive on any device and downloads as PDF in one click. The formatted
PDF/Word stay as best-effort attachments (delivered when they upload clean); this
text Google Doc is what guarantees the brief is ALWAYS readable (SKILL.md
Step 11).

Architecture (2026-06-19 recipe+cooks refactor):
- `brief_model` is the structure + rules authority; this module is the TEXT
  format backend, not a content authority. It consumes the same ordered list of
  typed block records that `brief_model.build_blocks()` produces and paints each
  with a dedicated painter (same shape as brief_docx / brief_pdf). The
  star-landing check, starred-flag stamping, and section-item source backstop are
  all done once in `build_blocks()`; the painters here only format. For item
  conventions (SectionItem, guard helpers, block types), see `brief_model` —
  those definitions live there.
- Dependency direction: this module imports from `brief_model` only; it does NOT
  import from brief_docx or brief_pdf.

The ★ is kept as the real Unicode glyph — Google Docs render it fine (no vector
trick needed, unlike the PDF backend). The trailing `assessment`/`draft` section
slots are retired (assessment 2026-06-15; draft — "Proposed Update for
Distribution" — 2026-06-18) and no longer rendered. Section items should be
`SectionItem` records (see `brief_model`); the builder also accepts the legacy
positional 7-tuple. exec items may be (name, line) or (name, line, links);
links render inline with URLs (plain text has no hyperlink markup).
"""
from brief_model import (
    build_blocks, HYGIENE_HEAD,
    TitleBlock, Heading1, ExecItem, CompanyItem,
    Bullet, Paragraph, PlainBullet, NumberedItem, Note,
)

STAR = "★"  # ★ — Google Docs renders Unicode natively (no vector trick needed)
RULE = "=" * 60


def _links_str(links):
    return "; ".join("%s (%s)" % (label, url) for label, url in links)


def _paint_title(out, b):
    """Paint a TitleBlock: the four header lines then one trailing blank."""
    out += ["PUBCO BRIEF", b.date_line,
            "PRIVILEGED & CONFIDENTIAL — FOR INTERNAL DISTRIBUTION",
            b.coverage_note, ""]


def _paint_heading1(out, b):
    """Paint a Heading1 block: RULE / heading text / RULE.

    Spacing rule: insert exactly one blank line before the heading only when the
    previous line isn't already blank. This adds NO blank before the first
    heading (the title block already ends with ""), supplies the single
    block-trailing blank after the exec/adjacent/market/trackers/catchup blocks
    (whose last item has no trailing blank), and adds NO extra blank after a
    company item (which already ends in its own trailing blank).
    """
    if out and out[-1] != "":
        out.append("")
    # Heading text is upper-cased for every heading EXCEPT the hygiene appendix.
    # The hygiene heading must keep its parenthetical LOWERCASE — emitting
    # HYGIENE_HEAD.upper() would wrongly uppercase "(proposed; not auto-applied)".
    # This preserves the historical text casing of that one heading.
    if b.text == HYGIENE_HEAD:
        head = "APPENDIX — WATCHLIST HYGIENE (proposed; not auto-applied)"
    else:
        head = b.text.upper()
    out += [RULE, head, RULE]


def _paint_exec(out, b):
    """Paint an ExecItem: numbered, optional star, optional inline source. No
    trailing blank (the next Heading1 supplies the block-trailing blank)."""
    star = (STAR + " ") if b.starred else ""
    # Sources inline so lead names promoted into the exec summary stay traceable
    # in the Google Doc (URLs carried, since plain text has no hyperlink markup).
    src = (" — Source: " + _links_str(b.links)) if b.links else ""
    out.append("%d. %s%s. %s%s" % (b.number, star, b.name, b.summary, src))


def _paint_company(out, b):
    """Paint a CompanyItem: star+name, source line, summary, optional
    assessment, then the per-item trailing blank."""
    star = (STAR + " ") if b.starred else ""
    out.append("%s%s" % (star, b.company))
    src = (" — Source: " + _links_str(b.links)) if b.links else ""
    out.append("  %s — %s%s" % (b.category, b.dateline, src))
    out.append("  " + b.summary)
    if b.assessment:
        out.append("  Assessment: " + b.assessment)
    # "Proposed Update for Distribution" (the _draft slot) was retired
    # 2026-06-18 at the principal's instruction — no longer rendered.
    out.append("")


def _paint_bullet(out, b):
    """Paint a Bullet (adjacent / market-notes shape). No trailing blank."""
    out.append("- %s — %s [%s: %s]" % (b.title, b.text, b.src_label, b.src_url))


def _paint_paragraph(out, b):
    """Paint a Paragraph (adjacent_note / string-body catchup). No trailing blank."""
    out.append(b.text)


def _paint_plain_bullet(out, b):
    """Paint a PlainBullet (trackers / list-body catchup). No trailing blank."""
    out.append("- " + b.text)


def _paint_numbered(out, b):
    """Paint a NumberedItem (hygiene list). No trailing blank."""
    out.append("%d. %s" % (b.number, b.text))


def _paint_note(out, b):
    """Paint a Note (the Market-Notes intro line, appended verbatim). No
    trailing blank."""
    out.append(b.text)


_PAINT = {
    TitleBlock:   _paint_title,
    Heading1:     _paint_heading1,
    ExecItem:     _paint_exec,
    CompanyItem:  _paint_company,
    Bullet:       _paint_bullet,
    Paragraph:    _paint_paragraph,
    PlainBullet:  _paint_plain_bullet,
    NumberedItem: _paint_numbered,
    Note:         _paint_note,
}


def render_text(blocks):
    """Paint a recipe block list into the complete plain-text brief and return it.

    Each painter appends to the shared `out` list; the final return trims any
    trailing whitespace and re-adds a single newline. The source-backstop, the
    star-landing check, and the starred-flag stamping were already done by
    build_blocks()."""
    out = []
    for b in blocks:
        _PAINT[type(b)](out, b)
    return "\n".join(out).rstrip() + "\n"


def render_brief_text(*, date_line, coverage_note, exec_items, sections, starred=(),
                      adjacent=(), adjacent_note=None, market_notes=(), trackers=(),
                      catchup=None, hygiene=()):
    """Return the complete brief as a clean, structured plain-text string.

    Signature, section order, and guards mirror brief_docx.render_brief exactly
    (the retired quiet/run_notes parameters are absent here too, so passing them
    raises TypeError). Upload the result via create_file textContent +
    contentMimeType 'text/plain' to land a Google Doc."""
    return render_text(build_blocks(
        date_line=date_line,
        coverage_note=coverage_note,
        exec_items=exec_items,
        sections=sections,
        starred=starred,
        adjacent=adjacent,
        adjacent_note=adjacent_note,
        market_notes=market_notes,
        trackers=trackers,
        catchup=catchup,
        hygiene=hygiene,
    ))
