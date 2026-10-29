"""
Per-call timeouts for L5 calls that have no native timeout (in-process model
inference, Chroma's HTTP client which is built with timeout=None).

The call runs on a bounded shared pool; the caller stops waiting after
`timeout_s`. A timed-out thread can't be killed and finishes in the
background, but the request (and the Celery worker) moves on.
"""

import concurrent.futures as cf
import time
from typing import Callable, Optional, TypeVar

T = TypeVar("T")

_POOL = cf.ThreadPoolExecutor(max_workers=8, thread_name_prefix="retrieval-call")


class CallTimeoutError(TimeoutError):
    pass


def budgeted_timeout(setting_s: float, deadline: Optional[float] = None) -> float:
    """
    min(per-call setting, time left before the request deadline).
    `deadline` is a time.monotonic() value; None means no request deadline.
    """
    if deadline is None:
        return setting_s
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise CallTimeoutError("request deadline already passed")
    return min(setting_s, remaining)


def call_with_timeout(fn: Callable[..., T], timeout_s: float, *args, **kwargs) -> T:
    future = _POOL.submit(fn, *args, **kwargs)
    try:
        return future.result(timeout=timeout_s)
    except cf.TimeoutError:
        future.cancel()
        name = getattr(fn, "__qualname__", repr(fn))
        raise CallTimeoutError(f"{name} exceeded {timeout_s}s") from None
