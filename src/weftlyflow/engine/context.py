"""ExecutionContext — the single object every node receives during execution.

Keeping nodes dependent on one well-defined context (rather than a grab-bag of
kwargs) makes the node contract stable across phases: Phase 4 layers
credential resolution and expression evaluation onto the existing surface
without changing the node signature.

Only the fields nodes *actually need* are exposed here. The executor holds a
larger :class:`~weftlyflow.engine.runtime.RunState` privately and hands nodes a
narrow view via this class.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from typing import TYPE_CHECKING, Any

from weftlyflow.config import get_settings
from weftlyflow.domain.constants import MAIN_PORT
from weftlyflow.expression.proxies import build_proxies, filter_env
from weftlyflow.expression.resolver import resolve, resolve_tree


@lru_cache(maxsize=1)
def _cached_exposed_env() -> dict[str, str]:
    """Snapshot the exposed-env subset once per process.

    ``os.environ`` is read exactly once per worker boot; expression
    evaluation then reads from this dict on the hot path. Clearing the
    cache is only needed in tests and is done via
    ``_cached_exposed_env.cache_clear()``.
    """
    allowlist = get_settings().exposed_env_var_list
    return filter_env(dict(os.environ), allowlist=allowlist)

if TYPE_CHECKING:
    from weftlyflow.binary.store import BinaryStore
    from weftlyflow.credentials.resolver import CredentialResolver
    from weftlyflow.domain.execution import ExecutionMode, Item
    from weftlyflow.domain.workflow import Node, Workflow
    from weftlyflow.engine.hooks import LifecycleHooks
    from weftlyflow.engine.subworkflow import SubWorkflowRunner


@dataclass(slots=True)
class ExecutionContext:
    """Per-node view of the current execution.

    Attributes:
        workflow: The immutable workflow snapshot being executed.
        execution_id: The ``ex_<ulid>`` identifier for this run.
        mode: How the execution was triggered.
        node: The node currently being executed.
        inputs: ``{port_name: [items]}`` — the inputs presented to this node.
        static_data: Mutable per-workflow key-value store (persisted across runs
            in Phase 2; in-memory only for Phase 1).
        hooks: Lifecycle hooks (defaults to a null implementation).
        canceled: Cooperative cancellation flag; nodes that do long work should
            check this periodically and bail out.
    """

    workflow: Workflow
    execution_id: str
    mode: ExecutionMode
    node: Node
    inputs: dict[str, list[Item]] = field(default_factory=dict)
    static_data: dict[str, Any] = field(default_factory=dict)
    hooks: LifecycleHooks | None = None
    canceled: bool = False
    credential_resolver: CredentialResolver | None = None
    sub_workflow_runner: SubWorkflowRunner | None = None
    binary_store: BinaryStore | None = None

    def param(self, name: str, default: Any = None) -> Any:
        """Return the raw parameter value — no expression evaluation.

        Use :meth:`resolved_param` when the value may contain ``{{ ... }}``.
        """
        return self.node.parameters.get(name, default)

    def resolved_param(
        self,
        name: str,
        default: Any = None,
        *,
        item: Item | None = None,
    ) -> Any:
        """Return the parameter with any ``{{ ... }}`` expressions resolved.

        If ``item`` is not provided, the first item on the main input port
        acts as the current row — matching the intuition that expressions in
        node parameters reference "the item about to be processed".
        """
        value = self.param(name, default)
        return resolve(value, self._proxies_for(item))

    def resolved_params(self, *, item: Item | None = None) -> dict[str, Any]:
        """Return every parameter with expressions resolved, preserving shape."""
        resolved: Any = resolve_tree(dict(self.node.parameters), self._proxies_for(item))
        assert isinstance(resolved, dict)
        return resolved

    def get_input(self, port: str = MAIN_PORT) -> list[Item]:
        """Return the items on input port ``port`` (empty list if unconnected)."""
        return self.inputs.get(port, [])

    async def load_credential(self, slot: str) -> tuple[Any, dict[str, Any]] | None:
        """Resolve the credential attached to ``slot`` on the current node.

        Returns ``None`` when the node has no credential for ``slot`` or when
        the execution was configured without a resolver. Raises on lookup
        errors so nodes can treat "found but broken" the same as any other
        failure.
        """
        credential_id = self.node.credentials.get(slot)
        if not credential_id or self.credential_resolver is None:
            return None
        cred_cls, payload = await self.credential_resolver.resolve(
            credential_id, project_id=self.workflow.project_id,
        )
        return cred_cls(), payload

    def _proxies_for(self, item: Item | None) -> dict[str, Any]:
        # Delayed import avoids a cycle; Item flows through the domain layer
        # which must stay dependency-free.
        from weftlyflow.domain.execution import Item as DomainItem  # noqa: PLC0415

        inputs = self.get_input(MAIN_PORT)
        current = item if item is not None else (inputs[0] if inputs else DomainItem())
        return build_proxies(
            item=current,
            inputs=inputs,
            workflow_id=self.workflow.id,
            workflow_name=self.workflow.name,
            project_id=self.workflow.project_id,
            execution_id=self.execution_id,
            execution_mode=self.mode,
            env_vars=_cached_exposed_env(),
        )
