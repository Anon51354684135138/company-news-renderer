# company-news-renderer

Pure-Python PDF / Word / plain-text renderer for the PubCo Brief (formatting
logic only — no deal data, no watchlist, no secrets). The Company News cloud
routine clones this repo and builds the brief's PDF with it
(`scripts/brief_pdf.py` via `save_all_formats`). Kept in sync with the canonical
copy in the private skills repo.

## Cloud build (since 2026-10-29)

The routine's environment **setup script** installs fpdf2 from `vendor/` before
Claude starts (an in-session install is blocked by the auto-mode classifier):

    pip install --no-index --find-links /home/user/company-news-renderer/vendor fpdf2

The routine then builds the PDF with one command, which prints `PDF_OK ...` or
`PDF_FAIL: <reason>` and writes the upload-ready `.b64` next to the PDF:

    cd "02 - Skill - Company News/scripts" && python3 build_pdf.py ../../brief.json "PubCo Brief (MM.DD.YY).pdf"
