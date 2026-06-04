import textwrap

from testrium.core import EXIT_CONFIG_ERROR, EXIT_FAILURE, EXIT_NO_TESTS, EXIT_SUCCESS, run_cli


def write_file(path, content):
    path.write_text(textwrap.dedent(content), encoding="utf-8")


def write_unit(path, name, init, events, entrypoint="test_case:run_unit", **kwargs):
    enabled = str(kwargs.get("enabled", True)).lower()
    ready_event = kwargs.get("ready_event")
    ready_timeout = kwargs.get("ready_timeout", 1)
    dependencies = kwargs.get("dependencies", [])
    timeout = kwargs.get("timeout", 2)

    ready_line = f'ready_event = "{ready_event}"' if ready_event else "ready_event = \"\""
    dependency_list = ", ".join(f'"{dependency}"' for dependency in dependencies)
    event_list = ", ".join(f'"{event}"' for event in events)

    write_file(
        path,
        f"""
        ["{name}"]
        init = {init}
        enabled = {enabled}
        entrypoint = "{entrypoint}"
        {ready_line}
        ready_timeout = {ready_timeout}
        timeout = {timeout}
        use_setup = false
        in-except = "Resume"
        unit_dependencies = [{dependency_list}]
        events = [{event_list}]
        """,
    )


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


def test_run_cli_runs_generated_template_circuit(tmp_path, monkeypatch):
    group = tmp_path / "test_generated"
    group.mkdir()

    assert run_cli(["gen", "config-template", str(group)]) == EXIT_SUCCESS

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


def test_run_cli_returns_no_tests_for_empty_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    assert run_cli(["run"]) == EXIT_NO_TESTS


def test_run_cli_fails_when_readiness_probe_is_missing(tmp_path, monkeypatch):
    group = tmp_path / "test_missing_ready"
    units = group / "units"
    units.mkdir(parents=True)

    write_file(
        group / "config.toml",
        """
        ["Configs"]
        units = ["source"]
        enabled = true
        timeout = 1
        """,
    )
    write_unit(
        units / "source.toml",
        "source",
        init=0,
        ready_event="source-ready",
        ready_timeout=0.2,
        events=["source-ready"],
    )
    write_file(
        group / "test_case.py",
        """
        def run_unit():
            return None
        """,
    )

    monkeypatch.chdir(tmp_path)

    assert run_cli(["run"]) == EXIT_FAILURE


def test_run_cli_fails_when_completion_probe_is_missing(tmp_path, monkeypatch):
    group = tmp_path / "test_missing_completion"
    units = group / "units"
    units.mkdir(parents=True)

    write_file(
        group / "config.toml",
        """
        ["Configs"]
        units = ["source"]
        enabled = true
        timeout = 0.4
        """,
    )
    write_unit(
        units / "source.toml",
        "source",
        init=0,
        ready_event="source-ready",
        ready_timeout=0.5,
        events=["source-ready", "finished"],
    )
    write_file(
        group / "test_case.py",
        """
        from testrium.modules.events import Events_Manager

        def run_unit():
            Events_Manager(Unit="source", path=".").Set_Event("source-ready")
        """,
    )

    monkeypatch.chdir(tmp_path)

    assert run_cli(["run"]) == EXIT_FAILURE


def test_run_cli_fails_when_unit_process_raises(tmp_path, monkeypatch):
    group = tmp_path / "test_failed_process"
    units = group / "units"
    units.mkdir(parents=True)

    write_file(
        group / "config.toml",
        """
        ["Configs"]
        units = ["source"]
        enabled = true
        timeout = 1
        """,
    )
    write_unit(
        units / "source.toml",
        "source",
        init=0,
        ready_event="source-ready",
        events=["source-ready", "finished"],
    )
    write_file(
        group / "test_case.py",
        """
        from testrium.modules.events import Events_Manager

        def run_unit():
            Events_Manager(Unit="source", path=".").Set_Event("source-ready")
            raise RuntimeError("expected failure")
        """,
    )

    monkeypatch.chdir(tmp_path)

    assert run_cli(["run"]) == EXIT_FAILURE


def test_run_cli_ignores_disabled_units(tmp_path, monkeypatch):
    group = tmp_path / "test_disabled_unit"
    units = group / "units"
    units.mkdir(parents=True)

    write_file(
        group / "config.toml",
        """
        ["Configs"]
        units = ["target", "source"]
        enabled = true
        timeout = 1
        """,
    )
    write_unit(
        units / "target.toml",
        "target",
        init=0,
        ready_event="target-ready",
        events=["target-ready"],
        entrypoint="test_case:run_target",
    )
    write_unit(
        units / "source.toml",
        "source",
        init=1,
        enabled=False,
        ready_event="source-ready",
        events=["source-ready"],
        entrypoint="test_case:run_source",
    )
    write_file(
        group / "test_case.py",
        """
        from testrium.modules.events import Events_Manager

        def run_target():
            Events_Manager(Unit="target", path=".").Set_Event("target-ready")

        def run_source():
            raise RuntimeError("disabled unit should not run")
        """,
    )

    monkeypatch.chdir(tmp_path)

    assert run_cli(["run"]) == EXIT_SUCCESS
