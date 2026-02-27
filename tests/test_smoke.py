"""
Master AI — Integration Test Suite
Runs against live server (localhost:9000)
Usage: pytest tests/test_smoke.py -v
"""
import os
import pytest
import httpx

BASE = "http://localhost:9000"
API_KEY = os.environ.get("MASTER_AI_API_KEY", "")

@pytest.fixture(scope="session")
def client():
    with httpx.Client(base_url=BASE, timeout=10) as c:
        yield c

@pytest.fixture(scope="session")
def auth_headers():
    return {"X-API-Key": API_KEY}

class TestHealth:
    def test_health_ok(self, client):
        r = client.get("/health")
        assert r.status_code == 200
        d = r.json()
        assert d["status"] == "ok"
        assert d["plugins"] == 9
        assert d["memory_available"] is True

    def test_health_schema(self, client):
        d = client.get("/health").json()
        assert "schema_version" in d
        assert d["autonomy"]["level"] == 3

class TestAuth:
    def test_no_key_rejected(self, client):
        r = client.get("/system/context")
        assert r.status_code == 401

    def test_bad_key_rejected(self, client):
        r = client.get("/system/context", headers={"X-API-Key": "wrong"})
        assert r.status_code == 401

    def test_system_context(self, client, auth_headers):
        r = client.get("/system/context", headers=auth_headers)
        assert r.status_code == 200
        d = r.json()
        assert d["service"] == "master_ai"

class TestPlugins:
    def test_plugins_list(self, client, auth_headers):
        r = client.get("/plugins", headers=auth_headers)
        assert r.status_code == 200

    def test_brain_stats(self, client, auth_headers):
        r = client.get("/brain/stats", headers=auth_headers)
        assert r.status_code == 200

class TestTasks:
    def test_tasks_list(self, client, auth_headers):
        r = client.get("/tasks", headers=auth_headers)
        assert r.status_code == 200

    def test_approvals_pending(self, client, auth_headers):
        r = client.get("/approvals/pending", headers=auth_headers)
        assert r.status_code == 200

class TestKnowledge:
    _kid = None

    def test_knowledge_list(self, client, auth_headers):
        r = client.get("/knowledge", headers=auth_headers)
        assert r.status_code == 200

    def test_knowledge_create(self, client, auth_headers):
        r = client.post("/knowledge", headers=auth_headers, json={
            "category": "test", "key": "_pytest_tmp", "value": "test_value"
        })
        assert r.status_code == 200
        d = r.json()
        TestKnowledge._kid = d.get("id") or d.get("knowledge_id")

    def test_knowledge_delete(self, client, auth_headers):
        if not TestKnowledge._kid:
            pytest.skip("no kid")
        r = client.delete(f"/knowledge/{TestKnowledge._kid}", headers=auth_headers)
        assert r.status_code == 200

class TestMemory:
    def test_memory_list(self, client, auth_headers):
        r = client.get("/memory", headers=auth_headers)
        assert r.status_code == 200

    def test_memory_stats(self, client, auth_headers):
        r = client.get("/memory/stats", headers=auth_headers)
        assert r.status_code == 200

class TestEvents:
    def test_events_list(self, client, auth_headers):
        r = client.get("/events", headers=auth_headers)
        assert r.status_code == 200

    def test_schema(self, client, auth_headers):
        r = client.get("/schema", headers=auth_headers)
        assert r.status_code == 200

class TestShift:
    def test_shift(self, client, auth_headers):
        r = client.get("/shift", headers=auth_headers)
        assert r.status_code == 200

    def test_daily_stats(self, client, auth_headers):
        r = client.get("/stats/daily", headers=auth_headers)
        assert r.status_code == 200

class TestRateLimit:
    def test_webhook_rate_limit(self, client):
        got_429 = False
        for _ in range(12):
            r = client.post("/webhook/event", json={"description": "x", "source": "test"},
                           headers={"X-Webhook-Token": "bad"})
            if r.status_code == 429:
                got_429 = True
                break
        assert got_429, "Should get 429 after 10 hits"

    def test_health_not_limited(self, client):
        for _ in range(15):
            r = client.get("/health")
            assert r.status_code == 200

class TestSecurity:
    def test_deploy_requires_auth(self, client):
        r = client.post("/deploy", json={"file_path": "x", "content": "x"})
        assert r.status_code == 401

    def test_ssh_requires_auth(self, client):
        r = client.post("/ssh/run", json={"cmd": "echo hi"})
        assert r.status_code == 401

class TestAudit:
    def test_audit_log(self, client, auth_headers):
        r = client.get("/audit", headers=auth_headers)
        assert r.status_code == 200

    def test_brain_diag(self, client, auth_headers):
        r = client.get("/brain/diag", headers=auth_headers)
        assert r.status_code == 200
