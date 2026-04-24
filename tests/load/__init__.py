"""Load / throughput test scaffolding.

Two tiers:

``locustfile.py``
    Drives a running Weftlyflow API from outside the process. Start the
    stack with ``make docker-up``, then ``make loadgen`` to open the
    Locust UI on http://localhost:8089.

``test_engine_throughput.py``
    In-process pytest suite marked ``load``. Wall-clock budget on the
    hottest engine paths. Run with ``make test-load``. Budgets are
    deliberately loose — they catch an order-of-magnitude regression,
    not a 5% one.
"""
