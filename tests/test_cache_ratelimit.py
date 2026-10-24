from app.config import settings
from tests.conftest import new_lead


def test_list_is_cached_then_invalidated_on_write(client, agent, redis_on):
    headers = agent[1]
    new_lead(client, headers)
    first = client.get("/leads", headers=headers)
    second = client.get("/leads", headers=headers)
    assert first.headers["X-Cache"] == "MISS"
    assert second.headers["X-Cache"] == "HIT"
    assert first.json() == second.json()

    new_lead(client, headers, email="second@acme.com")  # write bumps the cache version
    third = client.get("/leads", headers=headers)
    assert third.headers["X-Cache"] == "MISS"
    assert third.json()["total"] == 2


def test_cache_is_per_user(client, agent, agent2, redis_on):
    new_lead(client, agent[1])
    client.get("/leads", headers=agent[1])
    other = client.get("/leads", headers=agent2[1])
    assert other.headers["X-Cache"] == "MISS"
    assert other.json()["total"] == 0


def test_stats_cached(client, agent, redis_on):
    new_lead(client, agent[1])
    assert client.get("/leads/stats/summary", headers=agent[1]).headers["X-Cache"] == "MISS"
    assert client.get("/leads/stats/summary", headers=agent[1]).headers["X-Cache"] == "HIT"


def test_app_works_without_redis(client, agent):
    new_lead(client, agent[1])
    res = client.get("/leads", headers=agent[1])
    assert res.status_code == 200
    assert res.headers["X-Cache"] == "MISS"  # never a hit when Redis is off


def test_rate_limit_returns_429(client, redis_on, monkeypatch):
    monkeypatch.setattr(settings, "rate_limit_per_minute", 3)
    codes = [client.get("/health").status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]
    res = client.get("/health")
    assert res.headers["Retry-After"] == "60"
