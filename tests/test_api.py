"""API smoke test with the stub runner (no model calls) on scratch data."""

from __future__ import annotations

import time

from fastapi.testclient import TestClient


def wait_for(client: TestClient, run_id: str) -> dict:
    for _ in range(100):
        rec = client.get(f"/api/runs/{run_id}").json()
        if rec["status"] not in ("queued", "running"):
            return rec
        time.sleep(0.05)
    raise AssertionError("run did not finish")


def test_api_smoke():
    from backend.main import app

    with TestClient(app) as c:
        h = c.get("/api/health").json()
        assert h["ok"] and h["model"] == "gpt-6-luna" and h["mode"] == "stub"

        emails = c.get("/api/emails").json()["emails"]
        assert len(emails) == 20 and any(e["flagged"] for e in emails)
        assert c.put("/api/emails/selection", json={"email_ids": ["e01", "e10", "e15", "e08"]}).json()["selected"]

        assert c.post("/api/runs", json={"email_ids": []}).status_code == 422
        assert c.post("/api/runs", json={"email_ids": ["nope"]}).status_code == 422
        r = c.post("/api/runs", json={})
        assert r.status_code == 202
        run = wait_for(c, r.json()["run_id"])
        assert run["status"] == "finished", run
        assert run["email_flags"][0]["email_id"] == "e08"
        assert "usage" in run and "per_agent" in run["usage"]
        assert c.get(f"/api/runs/{run['run_id']}/events").json()["total"] > 0

        props = c.get("/api/proposals").json()["proposals"]
        by_email = {p["email_id"]: p for p in props}
        assert by_email["e01"]["status"] == "pending"
        assert by_email["e10"]["blocks"][0]["defense"] == "rules"
        assert by_email["e15"]["blocks"][0]["defense"] == "permission"

        pid = by_email["e01"]["id"]
        assert c.post(f"/api/proposals/{pid}/approve", json={"approver": ""}).status_code == 422
        ok = c.post(f"/api/proposals/{pid}/approve", json={"approver": "Jordan Ellery"})
        assert ok.status_code == 200
        line = next(l for l in c.get("/api/trackers/budget").json()["lines"] if l["line_id"] == "READ-02")
        assert line["spent_to_date"] == 4090.5 and line["changed_fields"] == ["spent_to_date"]
        x = c.get("/api/trackers/export.xlsx")
        assert x.status_code == 200 and x.content[:2] == b"PK"

        assert c.get("/api/chase/overdue").json()["owners"]
        assert c.get("/api/chase/drafts").json()["drafts"]
        assert c.get("/api/digest").json()["latest"]["digest"]["headline"].startswith("STUB")

        assert c.post("/api/reset", json={"confirm": False}).status_code == 400
        assert c.post("/api/reset", json={"confirm": "yes"}).status_code == 422
        res = c.post("/api/reset", json={"confirm": True}).json()
        assert res["checksums_match"]
        line = next(l for l in c.get("/api/trackers/budget").json()["lines"] if l["line_id"] == "READ-02")
        assert line["spent_to_date"] == 2850.0

        cors = c.options("/api/health", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"})
        assert "access-control-allow-origin" not in cors.headers
        cors = c.options("/api/health", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
        assert cors.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_paste_safety_and_imap_routes(monkeypatch):
    from backend.main import app

    for k in ("IMAP_HOST", "IMAP_USER", "IMAP_APP_PASSWORD"):
        monkeypatch.delenv(k, raising=False)
    with TestClient(app) as c:
        assert c.get("/api/imap/status").json() == {"configured": False}
        assert c.post("/api/imap/search", json={}).status_code == 404

        bad = c.post("/api/emails/paste", json={"from_email": "not-an-email", "subject": "x", "body": "too short"})
        assert bad.status_code == 422
        r = c.post("/api/emails/paste", json={
            "from_name": "Saoirse Calloway", "from_email": "saoirse.calloway@brightfutures.example",
            "subject": "Snacks", "body": "Hi Jordan, the fall workshop series (WP-16) is now 60% complete."})
        assert r.status_code == 202 and r.json()["email_id"] == "p001"
        run = wait_for(c, r.json()["run_id"])
        assert run["email_ids"] == ["p001"] and "per_email" in run
        emails = c.get("/api/emails").json()["emails"]
        assert next(e for e in emails if e["id"] == "p001")["origin"] == "pasted"

        s = c.get("/api/safety").json()
        assert [d["key"] for d in s["defenses"]] == ["untrusted_email", "grounding", "permission", "rules", "caps"]
        t = c.post("/api/safety/selftest").json()
        assert t["model_calls"] == 0 and t["total"] >= 20 and t["failed"] == 0

        c.post("/api/reset", json={"confirm": True})
        assert not any(e["id"] == "p001" for e in c.get("/api/emails").json()["emails"])
