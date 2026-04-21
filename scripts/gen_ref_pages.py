"""Generate one ``docs/reference/<module>.md`` page per Python module.

Executed by the ``mkdocs-gen-files`` plugin during ``mkdocs build`` and
``mkdocs serve``. Each generated page contains a single ``:::`` directive that
the ``mkdocstrings`` plugin then renders into a typed, docstring-driven API
reference mirroring the ``src/weftlyflow`` package tree.

Also writes ``docs/reference/SUMMARY.md`` so the ``mkdocs-literate-nav`` plugin
can auto-include new modules without hand-editing ``mkdocs.yml``.
"""

from __future__ import annotations

from pathlib import Path

import mkdocs_gen_files

SRC_ROOT = Path("src/weftlyflow")
DOC_ROOT = Path("reference")

nav = mkdocs_gen_files.Nav()

for path in sorted(SRC_ROOT.rglob("*.py")):
    module_rel = path.relative_to(SRC_ROOT).with_suffix("")
    parts = ("weftlyflow", *module_rel.parts)

    if parts[-1] == "__init__":
        parts = parts[:-1]
        doc_path = Path(*module_rel.parts[:-1], "index.md") if module_rel.parts[:-1] else Path("index.md")
    elif parts[-1].startswith("_"):
        continue
    else:
        doc_path = module_rel.with_suffix(".md")

    if not parts:
        continue

    full_doc_path = DOC_ROOT / doc_path
    ident = ".".join(parts)

    nav[parts[1:]] = doc_path.as_posix() if parts[1:] else "index.md"

    with mkdocs_gen_files.open(full_doc_path, "w") as f:
        print(f"# `{ident}`\n\n::: {ident}\n", file=f)

    mkdocs_gen_files.set_edit_path(full_doc_path, path)

with mkdocs_gen_files.open(DOC_ROOT / "SUMMARY.md", "w") as f:
    f.writelines(nav.build_literate_nav())
