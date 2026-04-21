"""Trigger and polling lifecycle manager.

Owns:
    manager.py   : :class:`ActiveTriggerManager` — activates/deactivates workflows,
                   registers webhooks, schedules polls, survives restarts.
    scheduler.py : APScheduler wrapper.
    poller.py    : generic loop that invokes ``BasePollerNode.poll()``.

The manager runs only on the elected leader instance (see §13.3 of the bible).

See IMPLEMENTATION_BIBLE.md §13.
"""

from __future__ import annotations
