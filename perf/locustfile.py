"""NFR 1 load test: search must answer in under 500 ms with 10,000 clinics and 100 users."""
import random

from locust import HttpUser, between, task

TOWNS = [(-1.2864, 36.8172), (-1.0388, 37.0834), (-1.5177, 37.2634), (-0.3031, 36.0800), (-0.0917, 34.7680)]
SPECS = ["", "ABA therapy", "Speech and language therapy", "Occupational therapy"]


class Parent(HttpUser):
    wait_time = between(1, 3)

    @task
    def search(self):
        lat, lng = random.choice(TOWNS)
        params = {
            "lat": lat + random.uniform(-0.1, 0.1),
            "lng": lng + random.uniform(-0.1, 0.1),
            "radius": random.choice([5, 10, 25, 50]),
        }
        spec = random.choice(SPECS)
        if spec:
            params["specialization"] = spec
        self.client.get("/api/therapists/search/", params=params, name="/api/therapists/search/")
