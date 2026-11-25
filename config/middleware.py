"""Adds how long the server took to each response (NFR 1)."""
import time


class ServerTimingMiddleware:
    """Puts the server's own processing time in the Server-Timing header, e.g. "app;dur=21.4"."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        start = time.perf_counter()
        response = self.get_response(request)
        ms = (time.perf_counter() - start) * 1000
        response["Server-Timing"] = f"app;dur={ms:.1f}"
        return response
