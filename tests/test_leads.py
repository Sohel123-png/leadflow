from tests.conftest import new_lead


def test_create_and_get_lead(client, agent):
    user, headers = agent
    lead = new_lead(client, headers)
    assert lead["status"] == "new"
    assert lead["owner_id"] == user.id
    res = client.get(f"/leads/{lead['id']}", headers=headers)
    assert res.status_code == 200
    assert res.json()["name"] == "Asha Rao"


def test_create_lead_validation(client, agent):
    res = client.post("/leads", json={"name": "", "email": "bad"}, headers=agent[1])
    assert res.status_code == 422


def test_agent_only_sees_own_leads(client, agent, agent2):
    mine = new_lead(client, agent[1], name="Mine")
    theirs = new_lead(client, agent2[1], name="Theirs", email="t@acme.com")
    listing = client.get("/leads", headers=agent[1]).json()
    assert listing["total"] == 1
    assert listing["items"][0]["name"] == "Mine"
    assert client.get(f"/leads/{theirs['id']}", headers=agent[1]).status_code == 404
    assert client.get(f"/leads/{mine['id']}", headers=agent2[1]).status_code == 404


def test_admin_sees_all_leads(client, agent, agent2, admin):
    new_lead(client, agent[1])
    new_lead(client, agent2[1], email="b@acme.com")
    assert client.get("/leads", headers=admin[1]).json()["total"] == 2


def test_pagination(client, agent):
    for i in range(5):
        new_lead(client, agent[1], name=f"Lead {i}", email=f"l{i}@acme.com")
    page1 = client.get("/leads?size=2&page=1&sort=name", headers=agent[1]).json()
    page3 = client.get("/leads?size=2&page=3&sort=name", headers=agent[1]).json()
    assert page1["total"] == 5 and page1["pages"] == 3
    assert [i["name"] for i in page1["items"]] == ["Lead 0", "Lead 1"]
    assert [i["name"] for i in page3["items"]] == ["Lead 4"]


def test_search_and_filters(client, agent):
    new_lead(client, agent[1], name="Ravi Kumar", email="ravi@zeta.com", company="Zeta", source="referral")
    new_lead(client, agent[1], name="Meera Shah", email="meera@acme.com", company="Acme", source="website")
    assert client.get("/leads?q=zeta", headers=agent[1]).json()["total"] == 1
    assert client.get("/leads?q=MEERA", headers=agent[1]).json()["total"] == 1
    assert client.get("/leads?source=referral", headers=agent[1]).json()["total"] == 1
    assert client.get("/leads?status=won", headers=agent[1]).json()["total"] == 0


def test_invalid_query_params(client, agent):
    assert client.get("/leads?size=1000", headers=agent[1]).status_code == 422
    assert client.get("/leads?page=0", headers=agent[1]).status_code == 422
    assert client.get("/leads?status=banana", headers=agent[1]).status_code == 422


def test_update_lead(client, agent):
    lead = new_lead(client, agent[1])
    res = client.patch(f"/leads/{lead['id']}", json={"company": "NewCo"}, headers=agent[1])
    assert res.status_code == 200
    assert res.json()["company"] == "NewCo"
    assert res.json()["name"] == "Asha Rao"


def test_status_pipeline(client, agent):
    lead = new_lead(client, agent[1])
    path = f"/leads/{lead['id']}/status"
    # new -> won is not allowed, it must go through contacted
    assert client.patch(path, json={"status": "won"}, headers=agent[1]).status_code == 409
    assert client.patch(path, json={"status": "contacted"}, headers=agent[1]).json()["status"] == "contacted"
    assert client.patch(path, json={"status": "won"}, headers=agent[1]).json()["status"] == "won"
    # won is final
    assert client.patch(path, json={"status": "lost"}, headers=agent[1]).status_code == 409


def test_status_invalid_value(client, agent):
    lead = new_lead(client, agent[1])
    res = client.patch(f"/leads/{lead['id']}/status", json={"status": "maybe"}, headers=agent[1])
    assert res.status_code == 422


def test_only_admin_can_assign_owner(client, agent, agent2, admin):
    lead = new_lead(client, agent[1])
    res = client.patch(f"/leads/{lead['id']}", json={"owner_id": agent2[0].id}, headers=agent[1])
    assert res.status_code == 403
    res = client.patch(f"/leads/{lead['id']}", json={"owner_id": agent2[0].id}, headers=admin[1])
    assert res.status_code == 200 and res.json()["owner_id"] == agent2[0].id
    res = client.patch(f"/leads/{lead['id']}", json={"owner_id": 9999}, headers=admin[1])
    assert res.status_code == 404


def test_agent_cannot_create_lead_for_someone_else(client, agent, agent2):
    res = client.post(
        "/leads",
        json={"name": "X", "email": "x@acme.com", "owner_id": agent2[0].id},
        headers=agent[1],
    )
    assert res.status_code == 403


def test_delete_is_admin_only(client, agent, admin):
    lead = new_lead(client, agent[1])
    assert client.delete(f"/leads/{lead['id']}", headers=agent[1]).status_code == 403
    assert client.delete(f"/leads/{lead['id']}", headers=admin[1]).status_code == 204
    assert client.get(f"/leads/{lead['id']}", headers=admin[1]).status_code == 404
    assert client.delete(f"/leads/{lead['id']}", headers=admin[1]).status_code == 404


def test_stats_summary(client, agent):
    a = new_lead(client, agent[1], email="a@acme.com")
    new_lead(client, agent[1], email="b@acme.com")
    client.patch(f"/leads/{a['id']}/status", json={"status": "contacted"}, headers=agent[1])
    stats = client.get("/leads/stats/summary", headers=agent[1]).json()
    assert stats == {"total": 2, "by_status": {"new": 1, "contacted": 1, "won": 0, "lost": 0}}
