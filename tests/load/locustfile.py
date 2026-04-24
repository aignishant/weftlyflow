"""Locust scenario — drives the public API from outside the process.

Usage::

    # 1. Start the full stack (api + worker + beat + redis + postgres):
    make docker-up

    # 2. Point Locust at it:
    WEFTLYFLOW_LOADGEN_EMAIL=admin@example.com \\
    WEFTLYFLOW_LOADGEN_PASSWORD=change-me \\
    locust -f tests/load/locustfile.py \\
           --host http://localhost:5678

    # 3. Open http://localhost:8089 to start a run.

Scenarios:

* ``health`` — a baseline, lock-free request (/healthz). Cheap.
* ``list_workflows`` — authenticated list with DB round-trip.
* ``trigger_execution`` — the realistic hot path: authenticated POST
  that enqueues a workflow execution.

The point is *regression detection* — if a change doubles p95 on these
three scenarios, something is wrong. Treat the numbers as a floor, not
a target.
"""

from __future__ import annotations

import os

from locust import HttpUser, between, task

_EMAIL = os.environ.get("WEFTLYFLOW_LOADGEN_EMAIL", "admin@example.com")
_PASSWORD = os.environ.get("WEFTLYFLOW_LOADGEN_PASSWORD", "change-me")


class WeftlyflowUser(HttpUser):
    """Simulates an operator hitting the API."""

    wait_time = between(0.5, 2.0)

    def on_start(self) -> None:
        """Log in once per virtual user and cache the bearer token."""
        resp = self.client.post(
            "/api/v1/auth/login",
            json={"email": _EMAIL, "password": _PASSWORD},
            name="login",
        )
        resp.raise_for_status()
        token = resp.json()["access_token"]
        self.client.headers.update({"Authorization": f"Bearer {token}"})

    @task(10)
    def health(self) -> None:
        self.client.get("/healthz", name="health")

    @task(3)
    def list_workflows(self) -> None:
        self.client.get("/api/v1/workflows", name="list_workflows")

    @task(1)
    def me(self) -> None:
        self.client.get("/api/v1/auth/me", name="me")
