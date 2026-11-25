"""NFR 1 load test: search must answer in under 500 ms with 10,000 clinics and 100 users.

Two rows are reported: the time Locust measured, and the server's own time from the Server-Timing header.
"""
import random
from urllib.parse import urlencode

from locust import FastHttpUser, between, task

TOWNS = [(-1.2864, 36.8172), (-1.0388, 37.0834), (-1.5177, 37.2634), (-0.3031, 36.0800), (-0.0917, 34.7680)]
SPECS = ["", "ABA therapy", "Speech and language therapy", "Occupational therapy"]


def server_ms(response):
    """Read "app;dur=21.4" from the Server-Timing header."""
    header = response.headers.get("Server-Timing", "")
    try:
        return float(header.split("dur=")[1])
    except (IndexError, ValueError):
        return None


class Parent(FastHttpUser):
    # FastHttpUser uses less CPU than HttpUser, so Locust takes less from the server on one laptop
    wait_time = between(1, 3)

    @task
    def search(self):
        lat, lng = random.choice(TOWNS)
        params = {
            "lat": round(lat + random.uniform(-0.1, 0.1), 5),
            "lng": round(lng + random.uniform(-0.1, 0.1), 5),
            "radius": random.choice([5, 10, 25, 50]),
        }
        spec = random.choice(SPECS)
        if spec:
            params["specialization"] = spec
        response = self.client.get("/api/therapists/search/?" + urlencode(params), name="/api/therapists/search/")
        ms = server_ms(response)
        if ms is not None:
            self.environment.events.request.fire(
                request_type="SERVER", name="search (server time)", response_time=ms,
                response_length=0, exception=None, context={},
            )
