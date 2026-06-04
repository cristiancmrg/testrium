# Testrium Implementation Roadmap

This roadmap keeps implementation work tied to the circuit-level E2E goals in the README and developer guide.

## Goal

Testrium must make local Python circuits reliable to test:

```text
declare units
start coordinated processes
emit probes
collect events
verify endpoint activation
measure latency and consistency
report pass/fail clearly
```

## Issue Map

| Issue | Area | Acceptance gate |
| --- | --- | --- |
| #22 | CLI/runtime reliability | `testrium run` has dependencies declared, returns meaningful exit codes, and can run the example circuit. |
| #23 | Config and unit validation | Invalid configs fail before execution; duplicate ordering, missing units, disabled units, dependencies, entrypoints, and legacy keys are handled consistently. |
| #24 | Orchestration and lifecycle | Unit entrypoints run as coordinated processes, start by order/dependencies, wait for readiness probes, and tear down cleanly. |
| #25 | Event/probe verification | Required probes, exception events, send/receive correlation, latency, orphan events, and duplicate keys are reported clearly. |

## Current MVP Gap Closure

| Gap | Implementation direction |
| --- | --- |
| Placeholder examples | Use a real source/target circuit scenario with entrypoints and probes. |
| Fixed sleeps | Wait for declared readiness probes with timeouts. |
| Loose unit config | Normalize and validate unit config before runtime. |
| Shared event DB path | Use an isolated runtime DB for each test group run. |
| Manual event scanning | Use framework-level required-probe verification. |
| Manual latency calculation | Correlate `Send` and `Receive` events by `EventKey`. |
| Ambiguous process state | Track lifecycle states for each unit. |
| Unclear results | Print probe, correlation, and runtime DB summaries. |

## Follow-Up Tracking Issues

| Issue | Purpose |
| --- | --- |
| #29 | Keep the roadmap, TODO markers, and issue map current. |
| #30 | Expand generated circuit scenario templates. |
| #31 | Add regression fixtures for runner failure modes. |
| #32 | Promote generic history metrics into a public API. |

## Acceptance Gates

The MVP is ready when:

1. A generated two-unit circuit can run locally.
2. Missing readiness probes fail with a timeout message.
3. Missing completion probes appear in the summary.
4. Orphan send/receive events fail the scenario.
5. Duplicate event keys fail the scenario.
6. Result metrics include total duration and average latency.
7. Existing direct `test_*` functions still run during migration.

## Non-Goals For This MVP

- Distributed multi-machine execution.
- Replacing direct function test tools.
- Dashboard polish.
- AI log analysis.
- Non-SQLite storage backends.
