"""Weftlyflow command-line interface.

This module exposes the `weftlyflow` CLI (installed via a `project.scripts` entry
in ``pyproject.toml``). It is intentionally thin: most commands dispatch to
functions that live inside the corresponding subpackage so the CLI remains a
presentation layer rather than a place where business logic accumulates.

Commands:
    start   : run the API server (``uvicorn``).
    worker  : run a Celery worker.
    beat    : run Celery Beat (schedules durable time-based triggers).
    db      : database migration subcommands (``upgrade``, ``downgrade``, ``revision``).
    export  : export a workflow as JSON.
    import  : import a workflow JSON file.
    version : print the installed Weftlyflow version.

Example:
    $ weftlyflow version
    0.1.0a0
    $ weftlyflow start --host 0.0.0.0 --port 5678
"""

from __future__ import annotations

import typer

from weftlyflow import __version__

app = typer.Typer(
    name="weftlyflow",
    help="Weftlyflow — workflow automation platform.",
    no_args_is_help=True,
    add_completion=False,
)


@app.command()
def version() -> None:
    """Print the installed Weftlyflow version and exit."""
    typer.echo(__version__)


@app.command()
def start(
    host: str = typer.Option("0.0.0.0", help="Bind address."),
    port: int = typer.Option(5678, help="Bind port."),
    reload: bool = typer.Option(False, help="Enable auto-reload (dev only)."),
) -> None:
    """Run the Weftlyflow API server (uvicorn).

    This is a thin wrapper around ``uvicorn.run`` for convenience; in production
    prefer launching uvicorn/gunicorn directly so you can tune workers, log
    formats, and lifespan behaviour.
    """
    # Deferred import — uvicorn is heavy; keep ``weftlyflow version`` fast.
    import uvicorn  # noqa: PLC0415

    uvicorn.run(
        "weftlyflow.server.app:app",
        host=host,
        port=port,
        reload=reload,
        factory=False,
    )


@app.command()
def worker() -> None:
    """Run a Celery worker (placeholder — delegates to the ``celery`` binary).

    Phase-0 stub. Prefer ``celery -A weftlyflow.worker.app worker ...`` until the
    worker module is fleshed out in Phase 3.
    """
    typer.echo("Run: celery -A weftlyflow.worker.app worker -l info", err=True)
    raise typer.Exit(code=1)


@app.command()
def beat() -> None:
    """Run Celery Beat (placeholder — see ``worker``)."""
    typer.echo("Run: celery -A weftlyflow.worker.app beat -l info", err=True)
    raise typer.Exit(code=1)


if __name__ == "__main__":  # pragma: no cover
    app()
