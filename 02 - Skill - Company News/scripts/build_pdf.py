"""One-command PDF build for the cloud morning routine (added 2026-10-29).

    python3 build_pdf.py content.json "PubCo Brief (MM.DD.YY).pdf"

content.json holds the render_brief_pdf keyword arguments (JSON lists stand in
for tuples). Builds the PDF with the tested renderer, runs the single-coverage
gate, writes <out>.b64 for the Drive base64 upload, and prints ONE status line:
    PDF_OK pages=N bytes=M pdf=<out> b64=<out>.b64
or  PDF_FAIL: <reason>      (exit 1 — the routine ships the Google Doc alone
                             and puts this reason in its notification)
"""
import base64
import json
import sys


def build(content_path, out):
    try:
        import fpdf  # noqa: F401
    except ImportError:
        raise RuntimeError("fpdf2 not installed - routine environment setup script "
                           "missing or failed (see routine-prompts/README.md)")
    from brief_model import assert_single_coverage
    from brief_pdf import render_brief_pdf, save_brief_pdf

    with open(content_path, encoding="utf-8") as f:
        content = json.load(f)
    assert_single_coverage(content["exec_items"], content["sections"])
    pdf = render_brief_pdf(**content)
    save_brief_pdf(pdf, out)
    with open(out, "rb") as f:
        data = f.read()
    if not data.startswith(b"%PDF") or b"%%EOF" not in data[-64:]:
        raise RuntimeError("written file is not a complete PDF")
    b64 = base64.b64encode(data).decode("ascii")
    if base64.b64decode(b64) != data:
        raise RuntimeError("base64 round-trip mismatch")
    with open(out + ".b64", "w", encoding="ascii") as f:
        f.write(b64)
    return pdf.pages_count, len(data)


def main(argv):
    if len(argv) != 3:
        print("PDF_FAIL: usage: build_pdf.py content.json out.pdf")
        return 1
    try:
        pages, size = build(argv[1], argv[2])
    except Exception as e:  # any failure -> one loud line, never a hand-rolled PDF
        print("PDF_FAIL: %s: %s" % (type(e).__name__, e))
        return 1
    print("PDF_OK pages=%d bytes=%d pdf=%s b64=%s.b64" % (pages, size, argv[2], argv[2]))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
