"""Entry point for `python -m weftlyflow ...`.

Delegates to the Typer app exposed by `weftlyflow.cli`.
"""

from __future__ import annotations

from weftlyflow.cli import app

if __name__ == "__main__":  # pragma: no cover
    app()
