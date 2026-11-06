"""Turn a '# %%' percent-format script into a Jupyter notebook.
Usage: python scripts/py_to_ipynb.py notebooks/analysis.py   (writes notebooks/analysis.ipynb)
"""
import re
import sys
from pathlib import Path

import nbformat
from nbformat.v4 import new_code_cell, new_markdown_cell, new_notebook

src = Path(sys.argv[1])
cells, kind, buf = [], None, []


def flush():
    text = "\n".join(buf).strip("\n")
    if kind and text:
        if kind == "md":
            text = "\n".join(re.sub(r"^# ?", "", ln) for ln in text.splitlines())
            cells.append(new_markdown_cell(text))
        else:
            cells.append(new_code_cell(text))


for line in src.read_text(encoding="utf-8").splitlines():
    m = re.match(r"# %%(\s*\[markdown\])?\s*$", line)
    if m:
        flush()
        kind, buf = ("md" if m.group(1) else "code"), []
    else:
        buf.append(line)
flush()
out = src.with_suffix(".ipynb")
nbformat.write(new_notebook(cells=cells), out)
print(f"Wrote {out} ({len(cells)} cells)")