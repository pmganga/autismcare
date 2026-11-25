"""Times every request (NFR 1) and keeps recent timings for the admin performance page."""
import time
from collections import deque

STARTED = time.time()
RECENT = deque(maxlen=2000)  # (finished at, path, status, ms) for this server process


class ServerTimingMiddleware:
    """Puts the server's own processing time in the Server-Timing header, e.g. "app;dur=21.4"."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.perf_counter()
        response = self.get_response(request)
        ms = (time.perf_counter() - start) * 1000
        response["Server-Timing"] = f"app;dur={ms:.1f}"
        if not request.path.startswith("/static/"):
            RECENT.append((time.time(), request.path, response.status_code, ms))
        return response
