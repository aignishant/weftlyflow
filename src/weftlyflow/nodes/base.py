"""Abstract base classes for Weftlyflow nodes.

Three shapes:
    BaseNode         : action node — runs when upstream data arrives.
    BaseTriggerNode  : webhook / event trigger — sets up external listeners.
    BasePollerNode   : interval-polled trigger — fetches from an API.

Every subclass declares a ``spec: ClassVar[NodeSpec]``. The registry keys nodes
by ``(spec.type, spec.version)`` so multiple versions of the same node can
coexist — existing workflows keep running on v1 after v2 ships.

Example:
    class HttpRequestNode(BaseNode):
        '''Make an HTTP request and emit the response body as a new item.'''

        spec = NodeSpec(
            type="weftlyflow.http_request",
            version=1,
            display_name="HTTP Request",
            description="Issue an HTTP request.",
            icon="icons/http.svg",
            category=NodeCategory.CORE,
            inputs=[Port(name="main")],
            outputs=[Port(name="main")],
            properties=[...],
        )

        async def execute(self, ctx, items):
            ...
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, ClassVar

if TYPE_CHECKING:
    from weftlyflow.domain.execution import Item
    from weftlyflow.domain.node_spec import NodeSpec


class BaseNode(ABC):
    """Abstract base for action nodes."""

    spec: ClassVar[NodeSpec]

    @abstractmethod
    async def execute(self, ctx: Any, items: list[Item]) -> list[list[Item]]:
        """Run the node once against ``items`` and return one list per output port.

        Args:
            ctx: :class:`weftlyflow.engine.context.ExecutionContext`. Exposes
                parameter access, credential resolution, HTTP helpers, and
                static-data accessors.
            items: Input items on port 0. (Multi-input nodes receive a combined
                list; a node that needs per-port access reads ``ctx.input_port(n)``.)

        Returns:
            ``[output_port_index][item_index]``. A node with one output port
            returns ``[[item1, item2, ...]]``.

        Raises:
            NodeExecutionError: on unrecoverable error. With
                ``continue_on_fail=True`` on the node, the engine converts the
                exception into an error item instead of propagating.
        """


class BaseTriggerNode(ABC):
    """Abstract base for webhook / event triggers."""

    spec: ClassVar[NodeSpec]

    @abstractmethod
    async def setup(self, ctx: Any) -> Any:
        """Register listeners (webhooks, event subscriptions).

        Called when the workflow is activated.

        Args:
            ctx: :class:`weftlyflow.triggers.manager.TriggerContext`.

        Returns:
            An opaque handle. The engine stores it and later passes it to
            :meth:`teardown` on deactivation.
        """

    @abstractmethod
    async def teardown(self, handle: Any) -> None:
        """Deregister listeners. Called when the workflow is deactivated."""


class BasePollerNode(ABC):
    """Abstract base for interval-polled triggers."""

    spec: ClassVar[NodeSpec]

    @abstractmethod
    async def poll(self, ctx: Any) -> list[Item] | None:
        """Poll the upstream source.

        Args:
            ctx: :class:`weftlyflow.triggers.poller.PollContext`. Exposes
                credentials and a cursor stored in workflow static data.

        Returns:
            A list of new items (possibly empty), or ``None`` if nothing changed.
            Returning ``None`` is preferred over ``[]`` when there is no change,
            so the engine can skip a workflow invocation entirely.
        """
