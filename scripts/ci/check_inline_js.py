"""Check that every inline <script> in the given HTML pages parses, with `node --check`.

    python scripts/ci/check_inline_js.py web/index.html docs/ref/*.html

Scripts with a src, empty ones and data blocks (type="application/json", importmaps, shaders…) are left out; a
type="module" script is checked as a module. Exits 1 if any fails.
"""
import os
import re
import subprocess
import sys
import tempfile

SCRIPT = re.compile(r"<script(?P<attrs>[^>]*)>(?P<body>.*?)</script\s*>", re.S | re.I)
TYPE = re.compile(r"""\btype\s*=\s*["']?([^"'\s>]+)""", re.I)
JS_TYPES = {"", "module", "text/javascript", "application/javascript"}


def main(paths):
    bad = checked = 0
    for path in paths:
        html = open(path, encoding="utf-8").read()
        for m in SCRIPT.finditer(html):
            attrs, body = m["attrs"], m["body"]
            kind = (TYPE.search(attrs) or [None, ""])[1].lower()
            if re.search(r"\bsrc\s*=", attrs, re.I) or not body.strip() or kind not in JS_TYPES:
                continue
            fd, tmp = tempfile.mkstemp(suffix=".mjs" if kind == "module" else ".js")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(body)
            try:
                r = subprocess.run(["node", "--check", tmp], capture_output=True, text=True)
            finally:
                os.unlink(tmp)
            checked += 1
            if r.returncode:
                bad += 1
                line = html.count("\n", 0, m.start()) + 1
                print(f"{path}: <script> at line {line} does not parse\n{r.stderr.strip()}")
    print(f"{checked} inline scripts checked, {bad} failed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
