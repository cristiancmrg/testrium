import textwrap

from testrium.core import EXIT_CONFIG_ERROR, EXIT_SUCCESS, run_cli


def write_file(path, content):
    path.write_text(textwrap.dedent(content), encoding="utf-8")


def test_run_cli_executes_two_unit_circuit(tmp_path, monkeypatch):
    group = tmp_path / "test_circuit"
    units = group / "units"
    units.mkdir(parents=True)

    write_file(
        group / "config.toml",
        """
        ["Configs"]
        units = ["target", "source"]
        enabled = true
        timeout = 10
        """,
    )
    write_file(
        units / "target.toml",
        """
        ["target"]
        init = 0
        enabled = true
        entrypoint = "test_case:run_target"
        ready_event = "target-ready"
        unit_dependencies = []
        events = ["target-ready", "command-received", "endpoint-activated"]
        in-except = "Resume"
        """,
    )
    write_file(
        units / "source.toml",
        """
        ["source"]
        init = 1
        enabled = true
        entrypoint = "test_case:run_source"
        ready_event = "source-ready"
        unit_dependencies = ["target"]
        events = ["source-ready", "command-sent", "response-received"]
        in-except = "Resume"
        """,
    )
    write_file(
        group / "test_case.py",
        """
        from testrium.modules.events import Events_Manager

        def run_target():
            events = Events_Manager(Unit="target", path=".")
            all_events = Events_Manager(Unit="*", path=".")
            events.Set_Event("target-ready")
            assert all_events.wait_for_event("command-sent", unit="source", timeout=5)
            events.Set_Event("command-received", event_type="Receive", event_key="request-001")
            events.Set_Event("endpoint-activated")

        def run_source():
            events = Events_Manager(Unit="source", path=".")
            all_events = Events_Manager(Unit="*", path=".")
            events.Set_Event("source-ready")
            events.Set_Event("command-sent", event_type="Send", event_key="request-001")
            assert all_events.wait_for_event("endpoint-activated", unit="target", timeout=5)
            events.Set_Event("response-received")
        """,
    )

    monkeypatch.chdir(tmp_path)

    assert run_cli(["run"]) == EXIT_SUCCESS


def test_run_cli_returns_config_error_for_invalid_group(tmp_path, monkeypatch):
    group = tmp_path / "test_bad_config"
    (group / "units").mkdir(parents=True)

    write_file(
        group / "config.toml",
        """
        ["Configs"]
        units = ["source", "source"]
        """,
    )

    monkeypatch.chdir(tmp_path)

    assert run_cli(["run"]) == EXIT_CONFIG_ERROR
