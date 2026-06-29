"""Audit logging helpers (FR-AUTH-005): safe write + client-IP extraction."""
from types import SimpleNamespace

from app.services import audit_service


# --- client_ip ---------------------------------------------------------------

def test_client_ip_extracts_host():
    req = SimpleNamespace(client=SimpleNamespace(host="203.0.113.7"))
    assert audit_service.client_ip(req) == "203.0.113.7"


def test_client_ip_none_when_missing():
    assert audit_service.client_ip(SimpleNamespace(client=None)) is None
    assert audit_service.client_ip(SimpleNamespace()) is None


# --- log_action_safe: never breaks the audited request -----------------------

async def test_log_action_safe_swallows_errors(monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("db down")

    monkeypatch.setattr(audit_service, "log_action", boom)
    # Must not raise even though the underlying write fails.
    await audit_service.log_action_safe(None, action="login", resource_type="auth")


async def test_log_action_safe_forwards_arguments(monkeypatch):
    seen = {}

    async def fake(db, user_id, action, resource_type, resource_id, details, ip_address):
        seen.update(
            user_id=user_id, action=action, resource_type=resource_type,
            resource_id=resource_id, details=details, ip_address=ip_address,
        )

    monkeypatch.setattr(audit_service, "log_action", fake)
    await audit_service.log_action_safe(
        None, user_id="u1", action="opportunity_updated", resource_type="opportunity",
        resource_id="o9", details={"fields": ["status"]}, ip_address="1.2.3.4",
    )
    assert seen == {
        "user_id": "u1", "action": "opportunity_updated", "resource_type": "opportunity",
        "resource_id": "o9", "details": {"fields": ["status"]}, "ip_address": "1.2.3.4",
    }
