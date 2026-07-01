"""Render-and-save orchestration for the PubCo Brief.

Sits on top of brief_model + the three cooks (so there is no import cycle).
save_all_formats builds the recipe once and writes all three formats — the
single home for the boilerplate every per-run generator used to repeat.
"""
from brief_docx import render_brief, save_brief
from brief_pdf import render_brief_pdf, save_brief_pdf
from brief_text import render_brief_text


def save_all_formats(content, out):
    """Build once, paint all three, save .docx/.pdf/.txt next to `out`.

    `out` must end in '.docx'. Versioning (' v2'/' v3') is the caller's job;
    save_brief/save_brief_pdf still refuse to overwrite an existing file."""
    pdf_out = out[:-5] + ".pdf"
    txt_out = out[:-5] + ".txt"
    save_brief(render_brief(**content), out)
    save_brief_pdf(render_brief_pdf(**content), pdf_out)
    with open(txt_out, "w", encoding="utf-8") as f:
        f.write(render_brief_text(**content))
    print("saved docx:", out)
    print("saved pdf :", pdf_out)
    print("saved txt :", txt_out)
