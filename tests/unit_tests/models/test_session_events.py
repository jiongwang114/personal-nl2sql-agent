import json

from dataengineer.api.services.chat_service import ChatService
from dataengineer.models.session_manager import SessionManager


def test_session_events_are_ordered_idempotent_and_redacted(tmp_path):
    manager = SessionManager(session_dir=str(tmp_path / "sessions"), scope="alice")

    first = manager.append_session_event(
        "pi_single_test",
        "tool_execution_start",
        {
            "tool_name": "list_tables",
            "api_key": "do-not-store",
            "input": {"query": "orders"},
        },
        event_id="run-1:tool-start",
    )
    duplicate = manager.append_session_event(
        "pi_single_test",
        "tool_execution_start",
        {"api_key": "different"},
        event_id="run-1:tool-start",
    )
    second = manager.append_session_event(
        "pi_single_test",
        "tool_execution_end",
        {"output": "Authorization: Bearer hidden-token"},
        event_id="run-1:tool-end",
    )

    assert first["sequence"] == 1
    assert second["sequence"] == 2
    assert duplicate == first
    assert first["payload"]["api_key"] == "[REDACTED]"
    assert "hidden-token" not in second["payload"]["output"]
    assert [item["event_type"] for item in manager.get_session_events("pi_single_test")] == [
        "tool_execution_start",
        "tool_execution_end",
    ]


def test_session_event_scope_isolated_and_history_keeps_legacy_messages(tmp_path):
    base_dir = str(tmp_path / "sessions")
    alice = SessionManager(session_dir=base_dir, scope="alice")
    bob = SessionManager(session_dir=base_dir, scope="bob")
    alice.append_session_event("shared", "agent_start", {}, event_id="alice-run")
    bob.append_session_event("shared", "agent_start", {}, event_id="bob-run")

    assert [item["event_id"] for item in alice.get_session_events("shared")] == ["alice-run"]
    assert [item["event_id"] for item in bob.get_session_events("shared")] == ["bob-run"]

    service = ChatService.__new__(ChatService)
    service._session_dir = base_dir
    history = service.get_history("shared", user_id="alice")
    assert history.success is True
    assert history.data.messages == []
    assert [item.event_id for item in history.data.events] == ["alice-run"]


def test_session_event_payload_is_structured_json(tmp_path):
    manager = SessionManager(session_dir=str(tmp_path / "sessions"))
    manager.append_session_event("structured", "progress", {"items": [1, 2]}, event_id="event-1")
    db_path = tmp_path / "sessions" / "structured.db"

    import sqlite3

    with sqlite3.connect(db_path) as conn:
        payload = conn.execute("SELECT payload FROM session_events WHERE event_id='event-1'").fetchone()[0]
    assert json.loads(payload) == {"items": [1, 2]}
