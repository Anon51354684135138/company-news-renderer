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

## Provenance

This repo belongs to the same owner as the daily-brief routine and Drive account;
the account name appears anonymized only because of a privacy mask. The wheels
below were downloaded unmodified from PyPI on 2026-07-08 via the `pip download`
command above. SHA256 (verifiable against pypi.org for each release):

    a352e7e428770286cc899e2542b6cdaedb2b4953ff269a210103ec58f6198a61  defusedxml-0.7.1-py2.py3-none-any.whl
    d76ac49f929aecaf82d83250b8347e099d7aecba0f4726c1d9b6df3b8bb5fe18  fonttools-4.63.0-cp311-cp311-manylinux2014_x86_64.manylinux_2_17_x86_64.whl
    d391fc508a3ce02fc43a577c830cda4fe6f37646f2d143d489839940932fbc19  fpdf2-2.8.7-py3-none-any.whl
    23d27a3e0307ec2244cc51e7287b919aa68d097504ebe19df4e76a98a3eea5bd  pillow-12.3.0-cp311-cp311-manylinux_2_27_x86_64.manylinux_2_28_x86_64.whl
