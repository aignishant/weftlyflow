"""Engine runtime constants — status tokens used inside the executor.

Port-name and index constants live in :mod:`weftlyflow.domain.constants`
because they are model-level vocabulary shared with nodes. This module keeps
engine-internal tokens only.
"""

from __future__ import annotations

from typing import Final, Literal

NodeStatus = Literal["success", "error", "disabled"]

STATUS_SUCCESS: Final[Literal["success"]] = "success"
STATUS_ERROR: Final[Literal["error"]] = "error"
STATUS_DISABLED: Final[Literal["disabled"]] = "disabled"
