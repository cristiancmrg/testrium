from testrium.modules.events import Events_Manager


def run_target():
    events = Events_Manager(Unit="target", path=".")
    all_events = Events_Manager(Unit="*", path=".")

    events.Set_Event("target-ready")
    if not all_events.wait_for_event("command-sent", unit="source", timeout=5):
        events.Set_Event("source-command-timeout", event_type="Exception")
        return

    events.Set_Event("command-received", event_type="Receive", event_key="request-001")
    events.Set_Event("endpoint-activated")


def run_source():
    events = Events_Manager(Unit="source", path=".")
    all_events = Events_Manager(Unit="*", path=".")

    events.Set_Event("source-ready")
    events.Set_Event("command-sent", event_type="Send", event_key="request-001")

    if all_events.wait_for_event("endpoint-activated", unit="target", timeout=5):
        events.Set_Event("response-received")
    else:
        events.Set_Event("response-timeout", event_type="Exception")
