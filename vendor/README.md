# Vendored wheels — offline install for the cloud brief routine

The claude.ai cloud environment that builds the daily PubCo Brief **cannot reach
PyPI** (egress blocked, confirmed by diagnostic 2026-07-08), so the PDF renderer's
dependencies are vendored here as wheels and installed offline:

    pip install --no-index --find-links vendor/ fpdf2

Wheels target the routine environment exactly: **CPython 3.11, x86_64 Linux
(glibc 2.39)**. If that environment's Python version ever changes, re-download with:

    pip download fpdf2 --dest vendor --only-binary=:all: --implementation cp \
      --python-version 3.11 --platform manylinux2014_x86_64 \
      --platform manylinux_2_28_x86_64 --platform any

(adjusting `--python-version`). Contents: fpdf2 + its full dependency closure
(Pillow, fonttools, defusedxml). Do not delete — the routine's PDF output dies
without these.
