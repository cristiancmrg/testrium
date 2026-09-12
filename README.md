# Testrium

Testrium is a circuit-level end-to-end testing framework for Python systems.

It is built for tests where the important question is not only "did this function return the right value?", but:

```text
Did this event, command, request, or message travel through the whole system correctly?
```

Testrium helps coordinate multiple Python processes, record probes from each unit, verify that the expected endpoints were activated, and measure latency and consistency across the full circuit.

## What Testrium Is For

Use Testrium when a test needs to prove behavior across multiple runtime units:

- a host and one or more clients
- two services exchanging messages
- an API that triggers a worker
- a producer writing to a queue and a consumer processing it
- a scheduler activating downstream logic
- a local microservice flow
- a module-to-module circuit where the final effect happens away from the source

Testrium is designed for tests where success means:

```text
processes started
units synchronized
events happened
messages crossed boundaries
expected probes completed
the target endpoint activated
latency and consistency were measured
the whole circuit passed
```

## What Testrium Is Not

Testrium is not a replacement for `pytest`, `unittest`, or direct API test tools.

Those tools are excellent for direct tests:

- function input/output
- class behavior
- isolated modules
- single endpoint responses
- fixtures and local assertions

Testrium sits beside them. It exists for the cases where direct assertions are not enough because the behavior crosses process, service, module, queue, socket, or callback boundaries.

## Why This Library Exists

In many systems, the actual behavior is a circuit:

```text
source unit -> event/message/request -> intermediate unit -> endpoint activation
```

Traditional test tools can test each piece, but the full circuit often becomes custom scripts, fixed sleeps, process joins, shared status flags, log scraping, and repeated manual assertions.

Testrium turns that repeated pattern into a framework:

```text
declare units
start coordinated processes
emit probes
collect events
verify the circuit
measure latency
report pass/fail
store history
```

## Core Concepts

### Unit

A unit is one actor in the scenario, such as `host`, `client`, `api`, `worker`, `scheduler`, or `consumer`.

### Probe

A probe is a completion tag emitted by a unit when something important happens.

Examples:

```text
host-ready
client-contacted
command-sent
command-received
worker-activated
response-received
```

### Event

An event is the stored record of a probe. Events include the unit, completed step, event type, event key, and timestamp.

### Circuit

A circuit is the full path from cause to effect.

Examples:

```text
client command -> host receives -> host callback runs -> client receives response
API request -> event emitted -> worker consumes -> database update completes
service A sends -> service B receives -> service B responds -> service A completes
```

## What Testrium Measures

Testrium should make these checks first-class:

| Circuit concern | What Testrium verifies |
| --- | --- |
| Start point | Which unit emitted the event or command |
| Route | Which units should receive or process it |
| Endpoint activation | Which callback, handler, worker, or endpoint ran |
| Completion tags | Which probes completed in each unit |
| Consistency | Whether `Send` and `Receive` pairs match by `EventKey` |
| Latency | Time between send/receive events and total scenario duration |
| Failure evidence | Missing probes, exception events, orphan sends, orphan receives, duplicate keys |

## Comparison

| Tool or category | Best for | Where Testrium fits |
| --- | --- | --- |
| `pytest` | Direct function, class, fixture, and module tests | Use Testrium when the assertion depends on events crossing runtime boundaries |
| `unittest` | Standard-library direct tests | Use Testrium for coordinated multi-unit scenarios |
| API test tools | One endpoint request/response | Use Testrium when the endpoint triggers async or downstream behavior |
| Contract testing | Schema/provider compatibility | Use Testrium to prove the live circuit actually executed |
| Browser E2E tools | UI flows | Use Testrium for backend/service/module circuits |
| Load tools | Throughput and stress | Use Testrium for per-circuit correctness and latency |
| Custom scripts | Project-specific orchestration | Use Testrium to avoid rebuilding process coordination and probe verification |

## Current Features

- Config-driven test groups
- Unit definitions through TOML files
- Config-first unit entrypoints using `module:function`
- Coordinated Python unit processes
- Unit lifecycle states and readiness probes
- Isolated SQLite runtime state per test group run
- Process-based setup support
- Event/probe logging with SQLite
- `Default`, `Exception`, `Send`, and `Receive` event types
- Required probe verification
- Send/receive correlation with latency metrics
- Callback hooks for extra validation and final result handling
- Basic result summaries
- Template generation for starter config files

The remaining near-term work is focused on richer fixtures, public history APIs, and broader reporting polish.

## Installation

Using Poetry:

```bash
poetry add testrium
```

Using pip:

```bash
pip install testrium
```

## Quick Start

Generate a starter config:

```bash
testrium gen config-template .
```

Run Testrium from a folder that contains test groups:

```bash
testrium run
```

Run with verbose logs:

```bash
testrium --verbose run
```

Exclude specific test groups:

```bash
testrium --less test_redirect run
```

## Example Shape

```text
tests/
  test_connection/
    config.toml
    setup.py
    test_case.py
    units/
      target.toml
      source.toml
```

Example unit config:

```toml
["source"]
init = 1
enabled = true
entrypoint = "test_case:run_source"
ready_event = "source-ready"
use_setup = false
in-except = "Resume"
unit_dependencies = ["target"]
events = [
  "source-ready",
  "command-sent",
  "response-received"
]
```

Example probe:

```python
from testrium.modules.events import Events_Manager

events = Events_Manager(Unit="source", path=".")

events.Set_Event("source-ready")
events.Set_Event("command-sent", event_type="Send", event_key="request-001")
```

The receiving unit can emit:

```python
from testrium.modules.events import Events_Manager

events = Events_Manager(Unit="target", path=".")

events.Set_Event("command-received", event_type="Receive", event_key="request-001")
```

Testrium can then verify that the expected probes happened and that the circuit completed.

## Documentation

- [Developer guide](docs/developer-guide.md): how to structure scenarios, units, probes, and circuit-level tests.
- [Design decisions](docs/design-decisions.md): architecture, module responsibilities, flow diagrams, and implementation direction.
- [Implementation roadmap](docs/implementation-roadmap.md): issue-aligned gaps, acceptance gates, and MVP follow-up work.

## Project Direction

The near-term implementation priority is:

1. Make the CLI runnable and dependency-complete.
2. Add strict config and unit validation.
3. Implement unit orchestration by order, dependency, and setup policy.
4. Implement event/probe verification.
5. Add event correlation and history metrics.

Testrium's core promise is simple:

```text
test the whole circuit, not only one component inside it
```

## License

Beginning with version 0.3.0, portions of Testrium owned by Cristian Camargo
Filho, trading as Zarpyon, are available under the
[PolyForm Small Business License 1.0.0](LICENSE-POLYFORM.md). Separate
commercial terms are available for uses outside that license.

Testrium releases through version 0.2.0 remain available under the MIT
License. Existing contributor-owned portions that were received under MIT
also remain under that license.

See [NOTICE.md](NOTICE.md) for exact scope and [AUTHORS.md](AUTHORS.md)
for project participants.
