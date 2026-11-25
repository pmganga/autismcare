"""NFR 1 load test: search must answer in < 500 ms with 10,000 clinics and 100 users.

1. python manage.py seed --bulk 10000
2. python manage.py runserver
3. pip install locust
4. locust -f perf/locustfile.py --host http://127.0.0.1:8000 --users 100 --spawn-rate 10 --run-time 2m --headless
   Look at the 95% column for /api/therapists/search/ in the summary. It should be under 500 ms.

Note: Django's runserver is a development server. For numbers you report,
run behind a production server (e.g. gunicorn on Linux).
"""
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
