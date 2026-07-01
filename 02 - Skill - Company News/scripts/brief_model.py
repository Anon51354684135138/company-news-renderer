"""Authority for the PubCo Brief's structure + content rules.

No rendering library is imported here. build_blocks() turns the per-run content
kwargs into an ordered list of typed "blocks" (the recipe), running the content
rules once and resolving the red-star membership, so brief_docx / brief_pdf /
brief_text become thin painters of that single list. See
docs/superpowers/specs/2026-06-19-render-recipe-design.md.
"""
import re
from collections import namedtuple

SectionItem  = namedtuple("SectionItem", "company category dateline links summary assessment")

TitleBlock   = namedtuple("TitleBlock", "date_line coverage_note")
Heading1     = namedtuple("Heading1", "text")
ExecItem     = namedtuple("ExecItem", "number name summary links starred")
CompanyItem  = namedtuple("CompanyItem", "company category dateline links summary assessment starred")
Bullet       = namedtuple("Bullet", "title text src_label src_url")
Paragraph    = namedtuple("Paragraph", "text")
PlainBullet  = namedtuple("PlainBullet", "text")
NumberedItem = namedtuple("NumberedItem", "number text")
Note         = namedtuple("Note", "text")

MARKET_NOTES_INTRO = "Broad-market items worth knowing this session — beyond the watchlist."
ADJACENT_HEADING   = "Adjacent-Market M&A Activity"
MARKET_NOTES_HEAD  = "Market Notes"
TRACKERS_HEAD      = "Story Trackers"
HYGIENE_HEAD       = "Appendix — Watchlist Hygiene (proposed; not auto-applied)"

# A display name's trailing "(TICKER)" — star entries may be given as bare
# tickers so name drift between runs can never silently drop a star.
_TICKER_RE = re.compile(r"\(([A-Z0-9.\-]{1,6})\)\s*$")


def _star_keys(display_name):
    keys = {display_name}
    m = _TICKER_RE.search(display_name)
    if m:
        keys.add(m.group(1))
    return keys


def _make_star_test(starred, exec_items, sections):
    """Return is_starred(name); raise if any starred entry never lands.

    A starred entry must match (by display name or bare ticker) at least one
    Executive Summary item OR at least one section company heading. Until
    2026-06-18 a star had to appear in BOTH places; the single-coverage rule
    (see assert_single_coverage) now puts a lead name in exactly one place, so
    "lands somewhere visible" is the right bar — a star that matches nothing is
    still the silent miss this guard exists to catch."""
    starred = set(starred)

    def is_starred(name):
        return bool(starred & _star_keys(name))

    if starred:
        names = ([e[0] for e in exec_items]
                 + [item[0] for _, items in sections for item in items])
        landed = set()
        for n in names:
            landed |= _star_keys(n)
        missing = [key for key in starred if key not in landed]
        if missing:
            raise ValueError("starred entries matched no Executive Summary item "
                             "or section heading: " + ", ".join(sorted(missing)))
    return is_starred


def _is_pseudo_entry(company, category):
    """True for the documented 'Briefs — <sector>' / 'Status' roll-up entries,
    which carry no single company and so are exempt from per-company rules."""
    return (category == "Status"
            or str(company).lstrip().startswith("Briefs")
            or str(category).lstrip().startswith("Briefs"))


def assert_single_coverage(exec_items, sections):
    """Raise if any company appears in BOTH the Executive Summary and a sector
    section.

    The single-coverage rule (principal, 2026-06-18): a lead name lives in
    exactly one place — promoted into the Executive Summary (with its source),
    or written up in a sector section, never both. 'Briefs'/'Status' roll-up
    pseudo-entries are exempt (they carry no single company).

    Enforced at the content-assembly layer: every per-run generator calls this
    before building, so a double-covered brief can never be produced. It is
    deliberately NOT called inside the renderers, so the renderers stay faithful
    formatting backends that can still reproduce historical (legitimately
    double-covered) briefs for the health-checkup baseline."""
    exec_keys = set()
    for e in exec_items:
        exec_keys |= _star_keys(e[0])
    dupes = []
    for _sector, items in sections:
        for item in items:
            company, category = item[0], item[1]
            if _is_pseudo_entry(company, category):
                continue
            if _star_keys(company) & exec_keys:
                dupes.append(company)
    if dupes:
        raise ValueError(
            "double coverage: these companies appear in BOTH the Executive "
            "Summary and a sector section — each lead name must appear in only "
            "one place (principal rule 2026-06-18): " + ", ".join(dupes))


def _normalize_item(item):
    """Accept the new 6-field SectionItem OR a legacy 6-/7-field tuple (the
    trailing retired `draft` slot is ignored) and return a SectionItem."""
    if isinstance(item, SectionItem):
        return item
    company, category, dateline, links, summary = item[0], item[1], item[2], item[3], item[4]
    assessment = item[5] if len(item) > 5 else None
    return SectionItem(company, category, dateline, links, summary, assessment)


def _require_source(company, category, dateline, links):
    """Section-item source backstop — identical rule + message to the three
    cooks' current inline copies. Briefs/Status roll-ups are exempt."""
    if _is_pseudo_entry(company, category):
        return
    if not links or not str(dateline).strip():
        raise ValueError(
            "section item %r is missing its dated source: every normal "
            "item needs non-empty links and a dateline (only Status/"
            "Briefs roll-up entries may omit them)" % (company,))


def build_blocks(*, date_line, coverage_note, exec_items, sections, starred=(),
                 adjacent=(), adjacent_note=None, market_notes=(), trackers=(),
                 catchup=None, hygiene=()):
    """Return the brief as an ordered list of block records (the recipe).

    Runs the star-landing check (and stamps `starred` on exec/company items) and
    the section-item source backstop. Does NOT enforce single-coverage — that is
    a driver-level call, because the renderers must still reproduce historical
    double-covered briefs for the baseline."""
    is_starred = _make_star_test(starred, exec_items, sections)
    blocks = [TitleBlock(date_line, coverage_note), Heading1("Executive Summary")]
    for i, entry in enumerate(exec_items, 1):
        name, line = entry[0], entry[1]
        links = entry[2] if len(entry) > 2 else None
        blocks.append(ExecItem(i, name, line, links, is_starred(name)))
    for sector, items in sections:
        blocks.append(Heading1(sector))
        for raw in items:
            it = _normalize_item(raw)
            _require_source(it.company, it.category, it.dateline, it.links)
            blocks.append(CompanyItem(it.company, it.category, it.dateline,
                                      it.links, it.summary, it.assessment,
                                      is_starred(it.company)))
    if adjacent or adjacent_note:
        blocks.append(Heading1(ADJACENT_HEADING))
        if adjacent:
            for title, text, src_label, src_url in adjacent:
                blocks.append(Bullet(title, text, src_label, src_url))
        else:
            blocks.append(Paragraph(adjacent_note))
    if market_notes:
        blocks.append(Heading1(MARKET_NOTES_HEAD))
        blocks.append(Note(MARKET_NOTES_INTRO))
        for title, text, src_label, src_url in market_notes:
            blocks.append(Bullet(title, text, src_label, src_url))
    if trackers:
        blocks.append(Heading1(TRACKERS_HEAD))
        for t in trackers:
            blocks.append(PlainBullet(t))
    if catchup:
        heading, body = catchup
        blocks.append(Heading1(heading))
        if isinstance(body, str):
            blocks.append(Paragraph(body))
        else:
            for line in body:
                blocks.append(PlainBullet(line))
    if hygiene:
        blocks.append(Heading1(HYGIENE_HEAD))
        for i, hline in enumerate(hygiene, 1):
            blocks.append(NumberedItem(i, hline))
    return blocks
