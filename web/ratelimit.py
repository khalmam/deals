"""A small in-memory limit for the public demo endpoint. The app runs as one process, so
memory is enough; a restart simply forgets the counts."""
import time
from collections import defaultdict, deque
from functools import wraps

from django.conf import settings
from django.http import JsonResponse

_by_client = defaultdict(deque)
_overall = deque()


def reset():
    _by_client.clear()
    _overall.clear()


def _client(request):
    """The last forwarded address is the one our own proxy added; earlier ones are spoofable."""
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "").split(",")[-1].strip()
    return forwarded or request.META.get("REMOTE_ADDR", "unknown")


def _trim(hits, now, window):
    while hits and now - hits[0] > window:
        hits.popleft()


def limited(view):
    @wraps(view)
    def inner(request, *args, **kwargs):
        now, window = time.monotonic(), settings.UI_NEGOTIATE_WINDOW_SECONDS
        mine = _by_client[_client(request)]
        _trim(mine, now, window)
        _trim(_overall, now, window)
        if len(mine) >= settings.UI_NEGOTIATE_PER_CLIENT or \
                len(_overall) >= settings.UI_NEGOTIATE_OVERALL:
            wait = int(window - (now - (mine[0] if mine else _overall[0]))) + 1
            reply = JsonResponse({"error": "Too many negotiations just now. Try again shortly."},
                                 status=429)
            reply["Retry-After"] = str(wait)
            return reply
        mine.append(now)
        _overall.append(now)
        return view(request, *args, **kwargs)
    return inner
