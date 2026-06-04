import json
import os
import time

import pandas as pd

from ..common.sql_pool import SQLiteConnectionPool


EVENT_DB_ENV = "TESTRIUM_EVENT_DB"
VALID_EVENT_TYPES = {"Default", "Exception", "Send", "Receive"}


def resolve_database_path(path: str | None) -> str:
    override = os.environ.get(EVENT_DB_ENV)
    if override:
        database_path = os.path.abspath(os.path.expanduser(override))
        os.makedirs(os.path.dirname(database_path), exist_ok=True)
        return database_path

    base_path = os.path.abspath(os.path.expanduser(path or "."))
    if base_path.lower().endswith(".db"):
        os.makedirs(os.path.dirname(base_path), exist_ok=True)
        return base_path

    os.makedirs(base_path, exist_ok=True)
    return os.path.join(base_path, "Data.db")


def _decode_metadata(value: str | None) -> dict:
    if not value:
        return {}
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return decoded if isinstance(decoded, dict) else {}


class Events_Manager:
    def __init__(self, Unit: str, path: str | None = "."):
        """
        Store and query unit probes.

        `Unit="*"` reads all units. When `TESTRIUM_EVENT_DB` is set by the
        runner, every process writes to that isolated run database regardless
        of the path passed by user code.
        """

        self.database_path = resolve_database_path(path)
        pool = SQLiteConnectionPool(3, self.database_path)
        self.connection = pool.get_connection()
        self.Unit = Unit
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        cur = self.connection.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS Events (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                Unit TEXT,
                StepCompleted TEXT,
                EventType TEXT,
                EventKey TEXT,
                Time NUMBER,
                Metadata TEXT
            )
            """
        )
        columns = {
            row[1]
            for row in cur.execute("PRAGMA table_info(Events)").fetchall()
        }
        if "Metadata" not in columns:
            cur.execute("ALTER TABLE Events ADD COLUMN Metadata TEXT")
        self.connection.commit()

    def drop_events_table(self) -> None:
        cur = self.connection.cursor()
        cur.execute("DROP TABLE IF EXISTS Events")
        self.connection.commit()
        self._ensure_schema()

    def list_events(self, unit: str | None = None) -> list[dict]:
        cur = self.connection.cursor()
        selected_unit = self.Unit if unit is None else unit

        if selected_unit == "*":
            rows = cur.execute(
                """
                SELECT ID, Unit, StepCompleted, EventType, EventKey, Time, Metadata
                FROM Events
                ORDER BY Time, ID
                """
            ).fetchall()
        else:
            rows = cur.execute(
                """
                SELECT ID, Unit, StepCompleted, EventType, EventKey, Time, Metadata
                FROM Events
                WHERE Unit = ?
                ORDER BY Time, ID
                """,
                (selected_unit,),
            ).fetchall()

        events = []
        for row in rows:
            events.append(
                {
                    "ID": row[0],
                    "Unit": row[1],
                    "StepCompleted": row[2],
                    "EventType": row[3],
                    "EventKey": row[4],
                    "Time": row[5],
                    "Metadata": _decode_metadata(row[6]),
                }
            )
        return events

    def List_Events(self) -> dict:
        columns = ["ID", "Unit", "StepCompleted", "EventType", "EventKey", "Time", "Metadata"]
        rows = [
            [
                event["ID"],
                event["Unit"],
                event["StepCompleted"],
                event["EventType"],
                event["EventKey"],
                event["Time"],
                event["Metadata"],
            ]
            for event in self.list_events()
        ]
        return pd.DataFrame(rows, columns=columns).to_dict()

    def Set_Event(self, step: str, event_type: str = "Default", **kwargs):
        if self.Unit == "*":
            raise ValueError("Can't set an event for generalized unit '*'")

        if event_type not in VALID_EVENT_TYPES:
            raise ValueError(
                "Event type can only be one of: "
                + ", ".join(sorted(VALID_EVENT_TYPES))
            )

        event_key = kwargs.pop("event_key", "")
        if event_type in {"Send", "Receive"} and not event_key:
            raise ValueError("Send and Receive events require event_key")

        metadata = kwargs.pop("metadata", {})
        if kwargs:
            metadata = {**metadata, **kwargs}
        if not isinstance(metadata, dict):
            raise ValueError("metadata must be a dictionary")

        cur = self.connection.cursor()
        cur.execute(
            """
            INSERT INTO Events (
                Unit,
                StepCompleted,
                EventType,
                EventKey,
                Time,
                Metadata
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                self.Unit,
                step,
                event_type,
                event_key,
                time.time(),
                json.dumps(metadata, sort_keys=True),
            ),
        )
        self.connection.commit()

    def completed_steps(self, unit: str | None = None) -> set[str]:
        return {
            event["StepCompleted"]
            for event in self.list_events(unit=unit)
        }

    def wait_for_event(
        self,
        step: str,
        unit: str | None = None,
        timeout: float = 10.0,
        poll_interval: float = 0.1,
    ) -> bool:
        deadline = time.time() + timeout
        while time.time() <= deadline:
            if step in self.completed_steps(unit=unit):
                return True
            time.sleep(poll_interval)
        return False

    def verify_required_events(self, units: list[dict]) -> dict:
        completed = []
        missing = []
        for unit in units:
            if not unit.get("enabled", True):
                continue
            unit_name = unit["name"]
            completed_steps = self.completed_steps(unit=unit_name)
            for step in unit.get("events", []):
                result = {"unit": unit_name, "step": step}
                if step in completed_steps:
                    completed.append(result)
                else:
                    missing.append(result)
        return {"completed": completed, "missing": missing}

    def correlate_send_receive(self) -> dict:
        sends: dict[str, list[dict]] = {}
        receives: dict[str, list[dict]] = {}
        for event in self.list_events(unit="*"):
            event_key = event.get("EventKey") or ""
            if not event_key:
                continue
            if event["EventType"] == "Send":
                sends.setdefault(event_key, []).append(event)
            elif event["EventType"] == "Receive":
                receives.setdefault(event_key, []).append(event)

        paired = []
        orphan_sends = []
        orphan_receives = []
        duplicate_keys = []

        for event_key in sorted(set(sends) | set(receives)):
            send_events = sends.get(event_key, [])
            receive_events = receives.get(event_key, [])
            if len(send_events) > 1 or len(receive_events) > 1:
                duplicate_keys.append(
                    {
                        "event_key": event_key,
                        "send_count": len(send_events),
                        "receive_count": len(receive_events),
                    }
                )
            if send_events and receive_events:
                first_send = send_events[0]
                first_receive = receive_events[0]
                paired.append(
                    {
                        "event_key": event_key,
                        "send_unit": first_send["Unit"],
                        "receive_unit": first_receive["Unit"],
                        "send_step": first_send["StepCompleted"],
                        "receive_step": first_receive["StepCompleted"],
                        "latency": max(0.0, first_receive["Time"] - first_send["Time"]),
                    }
                )
            elif send_events:
                orphan_sends.extend(send_events)
            elif receive_events:
                orphan_receives.extend(receive_events)

        latencies = [pair["latency"] for pair in paired]
        average_latency = sum(latencies) / len(latencies) if latencies else 0.0
        return {
            "paired": paired,
            "orphan_sends": orphan_sends,
            "orphan_receives": orphan_receives,
            "duplicate_keys": duplicate_keys,
            "average_latency": average_latency,
        }


class UnitStatus_Manager:
    VALID_STATES = {
        "created",
        "starting",
        "ready",
        "running",
        "finished",
        "failed",
        "stopped",
    }

    def __init__(self, path: str | None = "."):
        self.database_path = resolve_database_path(path)
        pool = SQLiteConnectionPool(3, self.database_path)
        self.connection = pool.get_connection()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        cur = self.connection.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS UnitStatus (
                Unit TEXT PRIMARY KEY,
                Status TEXT,
                UpdatedAt NUMBER
            )
            """
        )
        self.connection.commit()

    def set_status(self, unit: str, status: str) -> None:
        if status not in self.VALID_STATES:
            raise ValueError(
                "unit status must be one of: " + ", ".join(sorted(self.VALID_STATES))
            )
        cur = self.connection.cursor()
        cur.execute(
            """
            INSERT INTO UnitStatus (Unit, Status, UpdatedAt)
            VALUES (?, ?, ?)
            ON CONFLICT(Unit)
            DO UPDATE SET Status = excluded.Status, UpdatedAt = excluded.UpdatedAt
            """,
            (unit, status, time.time()),
        )
        self.connection.commit()

    def get_status(self, unit: str) -> str | None:
        cur = self.connection.cursor()
        row = cur.execute(
            "SELECT Status FROM UnitStatus WHERE Unit = ?",
            (unit,),
        ).fetchone()
        return row[0] if row else None

    def list_statuses(self) -> dict[str, str]:
        cur = self.connection.cursor()
        rows = cur.execute("SELECT Unit, Status FROM UnitStatus").fetchall()
        return {unit: status for unit, status in rows}


class Results_Manager:
    # TODO(#25): Promote this MVP result table into a public history API.
    def __init__(self, path: str | None = "."):
        self.database_path = resolve_database_path(path)
        pool = SQLiteConnectionPool(3, self.database_path)
        self.connection = pool.get_connection()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        cur = self.connection.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS Results (
                ID INTEGER PRIMARY KEY AUTOINCREMENT,
                TestGroup TEXT,
                Passed INTEGER,
                Duration NUMBER,
                AverageLatency NUMBER,
                Summary TEXT,
                Time NUMBER
            )
            """
        )
        self.connection.commit()

    def store_result(
        self,
        test_group: str,
        passed: bool,
        duration: float,
        average_latency: float,
        summary: dict,
    ) -> None:
        cur = self.connection.cursor()
        cur.execute(
            """
            INSERT INTO Results (
                TestGroup,
                Passed,
                Duration,
                AverageLatency,
                Summary,
                Time
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                test_group,
                int(passed),
                duration,
                average_latency,
                json.dumps(summary, sort_keys=True),
                time.time(),
            ),
        )
        self.connection.commit()
