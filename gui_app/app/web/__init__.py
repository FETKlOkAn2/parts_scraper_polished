"""Operator web console.

A FastAPI + HTMX UI that replaces the Tkinter operator GUI. The
Tkinter app stays in place; both call into the same ``Helper`` /
``Database`` / ``BatchWatermarkDetector`` classes underneath, so
adopting the web UI is a deployment swap, not a rewrite.

Entry point::

    uvicorn web.main:app --host 0.0.0.0 --port 8000

Production deployment puts uvicorn behind nginx (or directly behind
an ALB) and serves the static directory via the same route. For
intra-fleet operator use, ``uvicorn`` alone is sufficient.
"""
