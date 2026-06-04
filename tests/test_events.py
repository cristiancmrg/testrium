from testrium.modules.events import EVENT_DB_ENV, Events_Manager


def test_event_manager_uses_requested_path_and_lists_events(tmp_path):
    events = Events_Manager(Unit="source", path=str(tmp_path))
    events.Set_Event("source-ready")

    assert (tmp_path / "Data.db").exists()
    assert events.completed_steps(unit="source") == {"source-ready"}


def test_event_manager_creates_env_override_parent(tmp_path, monkeypatch):
    database_path = tmp_path / "runtime" / "Data.db"
    monkeypatch.setenv(EVENT_DB_ENV, str(database_path))

    Events_Manager(Unit="source", path=".").Set_Event("source-ready")

    assert database_path.exists()


def test_correlate_send_receive_pairs_and_latency(tmp_path):
    Events_Manager(Unit="source", path=str(tmp_path)).Set_Event(
        "command-sent",
        event_type="Send",
        event_key="request-001",
    )
    Events_Manager(Unit="target", path=str(tmp_path)).Set_Event(
        "command-received",
        event_type="Receive",
        event_key="request-001",
    )

    correlations = Events_Manager(Unit="*", path=str(tmp_path)).correlate_send_receive()

    assert len(correlations["paired"]) == 1
    assert correlations["paired"][0]["event_key"] == "request-001"
    assert correlations["orphan_sends"] == []
    assert correlations["orphan_receives"] == []
    assert correlations["duplicate_keys"] == []


def test_correlate_send_receive_reports_orphans_and_duplicates(tmp_path):
    source = Events_Manager(Unit="source", path=str(tmp_path))
    target = Events_Manager(Unit="target", path=str(tmp_path))

    source.Set_Event("command-sent", event_type="Send", event_key="duplicate")
    source.Set_Event("command-sent-again", event_type="Send", event_key="duplicate")
    target.Set_Event("unexpected-receive", event_type="Receive", event_key="orphan")

    correlations = Events_Manager(Unit="*", path=str(tmp_path)).correlate_send_receive()

    assert len(correlations["orphan_receives"]) == 1
    assert len(correlations["orphan_sends"]) == 2
    assert correlations["duplicate_keys"] == [
        {"event_key": "duplicate", "send_count": 2, "receive_count": 0}
    ]
