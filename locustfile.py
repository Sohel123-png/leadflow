"""Load test for the lead list/read endpoints.

    pip install locust
    locust -f locustfile.py --host http://localhost:8000 --headless -u 50 -r 10 -t 60s

Run it once with Redis on and once with REDIS_ENABLED=false, then compare the
median and p95 response times for `GET /leads`. Raise RATE_LIMIT_PER_MINUTE
(e.g. 100000) first, otherwise the rate limiter will answer 429.
"""
import random

from locust import HttpUser, between, task

SEARCH_TERMS = ["smith", "group", "inc", "john", "llc", "tech"]
STATUSES = ["new", "contacted", "won", "lost"]
SOURCES = ["website", "referral", "linkedin", "event"]


class LeadFlowUser(HttpUser):
    wait_time = between(0.1, 0.5)

    def on_start(self):
        res = self.client.post(
            "/auth/login",
            data={"username": "admin@leadflow.com", "password": "Admin@12345"},
        )
        self.client.headers.update({"Authorization": f"Bearer {res.json()['access_token']}"})

    @task(5)
    def list_leads(self):
        params = {"page": random.randint(1, 5), "size": 20}
        if random.random() < 0.5:
            params["status"] = random.choice(STATUSES)
        if random.random() < 0.3:
            params["source"] = random.choice(SOURCES)
        self.client.get("/leads", params=params, name="GET /leads")

    @task(3)
    def search_leads(self):
        self.client.get("/leads", params={"q": random.choice(SEARCH_TERMS)}, name="GET /leads?q=")

    @task(2)
    def stats(self):
        self.client.get("/leads/stats/summary", name="GET /leads/stats/summary")

    @task(1)
    def get_one(self):
        self.client.get(f"/leads/{random.randint(1, 1000)}", name="GET /leads/{id}")
