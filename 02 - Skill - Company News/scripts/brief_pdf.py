"""PDF painting backend for the PubCo Brief — a faithful "cook" that receives
the recipe from `brief_model.build_blocks()` and paints it into a PDF.

Why this exists (2026-06-16): briefs uploaded to Google Drive as Word (.docx)
files were arriving corrupted intermittently (a .docx is a ZIP; a few scrambled
bytes in transit kill the whole archive — confirmed: "Bad CRC-32 for
word/document.xml"). A PDF previews natively inline in Drive on any device, and
this module lets the skill ship one. The delivery step additionally verifies
every upload and re-sends on corruption (SKILL.md Step 11) — that guard is what
actually fixes the transit bug; the PDF is what makes the readable result land
where the reader can open it without Word.

Architecture (2026-06-19 recipe+cooks refactor):
- `brief_model` is the structure + rules authority; this module is a SECOND
  format backend, not a second content authority. It consumes the same ordered
  list of typed block records that `brief_model.build_blocks()` produces and
  paints each record with a dedicated painter. All structural helpers and guard
  logic (`_make_star_test`, `_is_pseudo_entry`, `assert_single_coverage`,
  `SectionItem`, etc.) live in `brief_model` — look there, not here. A drift
  guard (health-checkup/tests/test_pdf.py) asserts the PDF and Word brief carry
  the same text.
- Dependency direction: this module imports from `brief_model` only; it does NOT
  import from brief_docx.

Engine: fpdf2 — pure Python, pip-installable anywhere (including the cloud
routines, which have no Microsoft Word/LibreOffice). To avoid any external font
dependency we use fpdf2's built-in "Times" serif (visually ~indistinguishable
from Times New Roman for a text brief) and draw the red ★ as a vector polygon
(no glyph needed). Core fonts use cp1252 (WinAnsi) encoding for correct "•"
bullets — see the core_fonts_encoding note in render_brief_pdf. Text is
sanitized to Latin-1 first — see _sanitize — so rendering is always visually
correct with zero external-font dependency (the one deliberate fidelity
simplification vs. Word: em-dash → "-", curly → straight quotes).

Content conventions: section items should be `SectionItem` records (see
`brief_model`); the builder also accepts the legacy positional 7-tuple and
normalizes it. The trailing `assessment`/`draft` slots are retired (assessment
2026-06-15; draft 2026-06-18) and are no longer rendered. exec_items entries
may be (name, line) or (name, line, links) — the latter for lead names that
live only in the Executive Summary, with sources inline.
"""
import math
import os

from fpdf import FPDF

from brief_model import (
    build_blocks,
    TitleBlock, Heading1, ExecItem, CompanyItem,
    Bullet, Paragraph, PlainBullet, NumberedItem, Note,
)

FONT = "Times"
BLACK = (0, 0, 0)
RED = (0xFF, 0x00, 0x00)

# Page geometry (inches) — mirrors brief_docx: 0.5" margins on Letter.
MARGIN = 0.5
# Leave room at the bottom for the two-line confidentiality + page-number footer.
BOTTOM_MARGIN = 0.65

# The PDF uses fpdf2's built-in "Times" core font with WinAnsi (cp1252)
# encoding (see render_brief_pdf, which sets core_fonts_encoding="cp1252"). We
# normalize the exotic typographic/math glyphs briefs contain (em/en dashes,
# curly quotes, ellipsis, arrows, ≥/≤) to clean ASCII equivalents so rendering
# is always visually correct with zero external-font dependency (what lets the
# same code run in the cloud routines). The one deliberate fidelity
# simplification vs. the Word brief is typographic (em-dash -> "-", curly ->
# straight quotes); the information is identical.
#
# The round bullet "•" is INTENTIONALLY NOT mapped here: it is part of cp1252
# (byte 0x95) and renders as a real bullet under WinAnsiEncoding in every
# compliant PDF viewer. (Through 2026-06-17 it was mapped to MIDDLE DOT "·",
# U+00B7 — also valid WinAnsi — but with non-embedded core fonts some viewers,
# incl. Acrobat/Drive previews, substituted a .notdef box for it; the principal
# saw broken bullets. cp1252 + a real "•" fixes that for good — see
# health-checkup/tests/test_pdf.py.) The red star accent is drawn as a vector,
# so a stray literal star still degrades to "*".
_REPL = {
    "—": "-",            # EM DASH
    "–": "-",            # EN DASH
    "‑": "-",            # NON-BREAKING HYPHEN
    "‐": "-",            # HYPHEN
    "−": "-",            # MINUS SIGN
    "“": '"', "”": '"', "„": '"',   # curly double quotes
    "‘": "'", "’": "'", "‚": "'",   # curly single quotes / apostrophe
    "…": "...",          # HORIZONTAL ELLIPSIS
    "≈": "~",            # ALMOST EQUAL TO
    "≥": ">=",           # GREATER-THAN OR EQUAL TO
    "≤": "<=",           # LESS-THAN OR EQUAL TO
    "≠": "!=",           # NOT EQUAL TO
    "→": "->",           # RIGHTWARDS ARROW
    "←": "<-",           # LEFTWARDS ARROW
    "★": "*", "☆": "*",   # stars (the accent is drawn as a vector)
    "™": "(TM)", "€": "EUR",
    " ": " ", " ": " ", " ": " ",   # NBSP / thin / narrow NBSP
}


def _sanitize(text):
    """Return text rendered safe for fpdf2's cp1252 (WinAnsi) core fonts.

    Applies the explicit replacement map, then guarantees encodability so a rare
    unmapped exotic character degrades to '?' instead of raising mid-render.
    cp1252 (a superset of Latin-1) is used so the real round bullet "•" (0x95)
    survives and renders under WinAnsiEncoding; render_brief_pdf sets the
    matching core_fonts_encoding."""
    if text is None:
        return ""
    s = "".join(_REPL.get(ch, ch) for ch in str(text))
    return s.encode("cp1252", "replace").decode("cp1252")


class _Brief(FPDF):
    """Letter-page brief with the firm confidentiality + page-number footer."""

    def footer(self):
        self.set_y(-BOTTOM_MARGIN)
        self.set_font(FONT, "", 8)
        self.set_text_color(*BLACK)
        self.cell(0, 0.15,
                  _sanitize("Privileged & Confidential — For Internal Distribution"),
                  align="C", new_x="LMARGIN", new_y="NEXT")
        self.cell(0, 0.15, str(self.page_no()), align="C")


def _draw_star(pdf, x, y, R=0.058):
    """Draw a filled red 5-point star with its top point at x, vertical band
    starting at y (so it sits beside a line of text). Pure vector — no font."""
    cx, cy = x + R, y + R + 0.01
    r = R * 0.40
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rad = R if i % 2 == 0 else r
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    pdf.set_fill_color(*RED)
    pdf.polygon(pts, style="F")
    pdf.set_fill_color(*BLACK)


def _heading1(pdf, text):
    pdf.ln(0.10)
    pdf.set_font(FONT, "B", 13)
    pdf.set_text_color(*BLACK)
    pdf.multi_cell(0, 0.22, _sanitize(text), new_x="LMARGIN", new_y="NEXT")
    pdf.ln(0.02)


def _heading2(pdf, text, starred):
    pdf.ln(0.06)
    x0 = pdf.l_margin
    y0 = pdf.get_y()
    pdf.set_font(FONT, "B", 11.5)
    pdf.set_text_color(*BLACK)
    if starred:
        _draw_star(pdf, x0, y0)
        pdf.set_xy(x0 + 0.18, y0)
        pdf.multi_cell(0, 0.20, _sanitize(text), new_x="LMARGIN", new_y="NEXT")
        pdf.set_x(x0)
    else:
        pdf.multi_cell(0, 0.20, _sanitize(text), new_x="LMARGIN", new_y="NEXT")


def _source_line(pdf, category, dateline, links):
    """category — dateline — Source: <link>; <link>.  with inline black,
    underlined, clickable links (mirrors brief_docx.add_hyperlink styling)."""
    h = 0.175
    pdf.set_text_color(*BLACK)
    pdf.set_font(FONT, "", 11)
    pdf.write(h, _sanitize("%s — %s" % (category, dateline)))
    if links:
        pdf.write(h, _sanitize(" — Source: "))
        for i, (label, url) in enumerate(links):
            if not label or not url:
                # mirror brief_docx.add_hyperlink: an empty label/url renders an
                # invisible link, so fail loudly instead.
                raise ValueError("source link requires non-empty label and url")
            if i:
                pdf.write(h, "; ")
            pdf.set_font(FONT, "U", 11)
            pdf.write(h, _sanitize(label), link=url)
            pdf.set_font(FONT, "", 11)
        pdf.write(h, ".")
    pdf.ln(h)


def _indented_block(pdf, label, body, italic_body):
    """A 0.3"-indented paragraph: bold label then body (italic if italic_body)."""
    left = pdf.l_margin
    pdf.set_left_margin(left + 0.3)
    pdf.set_x(left + 0.3)
    h = 0.175
    pdf.set_text_color(*BLACK)
    pdf.set_font(FONT, "B", 11)
    pdf.write(h, _sanitize(label))
    pdf.set_font(FONT, "I" if italic_body else "", 11)
    pdf.write(h, _sanitize(body))
    pdf.ln(h)
    pdf.set_left_margin(left)
    pdf.set_x(left)


def _bullet(pdf, title, text, src_label, src_url):
    """· <bold title> — <text> [<link>]   (adjacent / market-notes shape)."""
    h = 0.175
    pdf.set_text_color(*BLACK)
    pdf.set_font(FONT, "", 11)
    pdf.write(h, _sanitize("•  "))
    pdf.set_font(FONT, "B", 11)
    pdf.write(h, _sanitize("%s — " % title))
    pdf.set_font(FONT, "", 11)
    pdf.write(h, _sanitize("%s [" % text))
    if not src_label or not src_url:
        raise ValueError("bullet requires non-empty source label and url")
    pdf.set_font(FONT, "U", 11)
    pdf.write(h, _sanitize(src_label), link=src_url)
    pdf.set_font(FONT, "", 11)
    pdf.write(h, "]")
    pdf.ln(h)


def _plain_bullet(pdf, text):
    h = 0.175
    left = pdf.l_margin
    pdf.set_text_color(*BLACK)
    pdf.set_font(FONT, "", 11)
    pdf.set_left_margin(left + 0.15)
    pdf.set_x(left + 0.15)
    pdf.write(h, _sanitize("•  " + text))
    pdf.ln(h)
    pdf.set_left_margin(left)
    pdf.set_x(left)


def _paint_title(pdf, b):
    """Paint a TitleBlock: centered PUBCO BRIEF header."""
    pdf.set_font(FONT, "B", 16)
    pdf.cell(0, 0.30, _sanitize("PUBCO BRIEF"), align="C",
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(FONT, "", 11)
    pdf.cell(0, 0.22, _sanitize(b.date_line), align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(FONT, "B", 9)
    pdf.cell(0, 0.20,
             _sanitize("PRIVILEGED & CONFIDENTIAL — FOR INTERNAL DISTRIBUTION"),
             align="C", new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(FONT, "I", 10)
    pdf.multi_cell(0, 0.18, _sanitize(b.coverage_note), align="C",
                   new_x="LMARGIN", new_y="NEXT")


def _paint_heading1(pdf, b):
    """Paint a Heading1 block."""
    _heading1(pdf, b.text)


def _paint_exec(pdf, b):
    """Paint an ExecItem block: numbered, bold name, optional inline links."""
    left = pdf.l_margin
    y0 = pdf.get_y()
    h = 0.175
    if b.starred:
        _draw_star(pdf, left, y0)
        pdf.set_xy(left + 0.18, y0)
    else:
        pdf.set_xy(left, y0)
    pdf.set_text_color(*BLACK)
    pdf.set_font(FONT, "B", 11)
    pdf.write(h, _sanitize("%d. %s. " % (b.number, b.name)))
    pdf.set_font(FONT, "", 11)
    pdf.write(h, _sanitize(b.summary))
    if b.links:
        # Inline sources so lead names promoted into the exec summary stay
        # traceable (mirrors the section source line's black underlined links).
        pdf.write(h, _sanitize(" ["))
        for j, (label, url) in enumerate(b.links):
            if not label or not url:
                raise ValueError("exec source link requires non-empty label and url")
            if j:
                pdf.write(h, "; ")
            pdf.set_font(FONT, "U", 11)
            pdf.write(h, _sanitize(label), link=url)
            pdf.set_font(FONT, "", 11)
        pdf.write(h, "]")
    pdf.ln(h)
    pdf.set_x(left)
    pdf.ln(0.04)


def _paint_company(pdf, b):
    """Paint a CompanyItem block: heading2, source line, body, optional assessment."""
    _heading2(pdf, b.company, b.starred)
    _source_line(pdf, b.category, b.dateline, b.links)
    pdf.set_text_color(*BLACK)
    pdf.set_font(FONT, "", 11)
    pdf.multi_cell(0, 0.175, _sanitize(b.summary), align="J",
                   new_x="LMARGIN", new_y="NEXT")
    if b.assessment:
        _indented_block(pdf, "Assessment: ", b.assessment, italic_body=False)


def _paint_bullet(pdf, b):
    """Paint a Bullet block."""
    _bullet(pdf, b.title, b.text, b.src_label, b.src_url)


def _paint_paragraph(pdf, b):
    """Paint a Paragraph block: justified multi_cell."""
    pdf.set_font(FONT, "", 11)
    pdf.multi_cell(0, 0.175, _sanitize(b.text), align="J",
                   new_x="LMARGIN", new_y="NEXT")


def _paint_plain_bullet(pdf, b):
    """Paint a PlainBullet block."""
    _plain_bullet(pdf, b.text)


def _paint_numbered(pdf, b):
    """Paint a NumberedItem block (hygiene list)."""
    h = 0.175
    left = pdf.l_margin
    pdf.set_font(FONT, "", 11)
    pdf.set_left_margin(left + 0.15)
    pdf.set_x(left + 0.15)
    pdf.write(h, _sanitize("%d. %s" % (b.number, b.text)))
    pdf.ln(h)
    pdf.set_left_margin(left)
    pdf.set_x(left)
    pdf.ln(0.02)


def _paint_note(pdf, b):
    """Paint a Note block: italic 9pt intro line."""
    pdf.set_font(FONT, "I", 9)
    pdf.multi_cell(0, 0.16, _sanitize(b.text), new_x="LMARGIN", new_y="NEXT")


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


def render_pdf(blocks):
    """Paint a recipe block list onto a new Letter PDF and return it.

    Creates the fpdf2 object, sets encoding/margins/page, then dispatches
    each block to its painter via _PAINT. The source-backstop, star-landing
    check, and starred-flag stamping were already done by build_blocks()."""
    pdf = _Brief(orientation="P", unit="in", format="Letter")
    # WinAnsi (cp1252) so the real round bullet "•" (0x95) and other cp1252
    # punctuation render under the core Times font instead of a .notdef box.
    pdf.core_fonts_encoding = "cp1252"
    pdf.set_margins(MARGIN, MARGIN, MARGIN)
    pdf.set_auto_page_break(True, margin=BOTTOM_MARGIN)
    pdf.set_text_color(*BLACK)
    pdf.add_page()
    for b in blocks:
        _PAINT[type(b)](pdf, b)
    return pdf


def render_brief_pdf(*, date_line, coverage_note, exec_items, sections, starred=(),
                     adjacent=(), adjacent_note=None, market_notes=(), trackers=(),
                     catchup=None, hygiene=()):
    """Build and return the complete brief as an fpdf2 PDF (bytes via .output()).

    Signature, section order, and guards mirror brief_docx.render_brief exactly
    so a per-run generator can hand the identical content to both. Parameters are
    documented in brief_docx.render_brief; the retired quiet/run_notes parameters
    are intentionally absent here too, so passing them raises TypeError."""
    return render_pdf(build_blocks(
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


def save_brief_pdf(pdf, out):
    """Save the PDF, refusing to overwrite an existing file (mirrors
    brief_docx.save_brief: versioning ' v2'/' v3' is the caller's job, and this
    guard stops a re-run from clobbering a shipped deliverable)."""
    if os.path.exists(out):
        raise FileExistsError(
            "refusing to overwrite existing brief: %s — pick the next "
            "' v2'/' v3' name per SKILL.md Step 11" % out)
    pdf.output(out)
