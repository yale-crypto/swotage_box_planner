"""
Gunicorn settings for the Stowage web app.

Packing is CPU-bound and runs inside the request, so the shape that matters is:
one slow request must not be able to hold the service, and it must not be able
to hold a worker indefinitely.

  · PACK_TIME_BUDGET_S (see webapp/app.py) bounds the search itself, which is
    what keeps a hard request from turning into a multi-minute one.
  · `timeout` is the backstop for anything that escapes that — well above the
    budget, because the search checks its deadline between plans and so can
    overshoot by one plan, but far below the old 120s.
  · Workers are processes, not threads: the work is Python bytecode holding the
    GIL, so threads would not add throughput.

Every value can be overridden through the environment.
"""

import multiprocessing
import os


def _int(name: str, default: int) -> int:
    try:
        return max(1, int(os.environ.get(name, default)))
    except ValueError:
        return default


bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"

# One worker per core saturates the CPU without oversubscribing it; small
# instances (Render's free plan reports many cores but grants a fraction of
# one) should pin this with WEB_CONCURRENCY.
workers = _int("WEB_CONCURRENCY", min(4, multiprocessing.cpu_count()))

# Long enough for a bounded search plus its overshoot, short enough that a stuck
# worker is recycled while someone is still watching the page.
timeout = _int("GUNICORN_TIMEOUT", 45)
graceful_timeout = _int("GUNICORN_GRACEFUL_TIMEOUT", 30)
keepalive = _int("GUNICORN_KEEPALIVE", 5)

# Recycle workers periodically: bounds the damage from any leak in a long-lived
# process. The jitter stops every worker recycling on the same request.
max_requests = _int("GUNICORN_MAX_REQUESTS", 1000)
max_requests_jitter = _int("GUNICORN_MAX_REQUESTS_JITTER", 100)

# Load the app before forking so workers share its pages, and a boot-time error
# fails the deploy rather than every request.
preload_app = True

accesslog = "-"
errorlog = "-"
