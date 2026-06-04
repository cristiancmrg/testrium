import argparse
import importlib
import importlib.util
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from multiprocessing import Process

from colorama import Fore, init

from testrium.common.generator.main import resolve_template
from testrium.common.loaders import (
    discover_tests,
    load_config,
    load_special_callbakcs,
    load_test_functions,
)
from testrium.common.utils import print_banner, suppress_output
from testrium.modules.events import (
    EVENT_DB_ENV,
    Events_Manager,
    Results_Manager,
    UnitStatus_Manager,
)
from testrium.tools.benchmark import run_machine_benchmark, save_benchmark_result


init(autoreset=True)

EXIT_SUCCESS = 0
EXIT_FAILURE = 1
EXIT_NO_TESTS = 2
EXIT_CONFIG_ERROR = 3


def handle_exception(test_name: str, start_time, error: object) -> dict:
    elapsed_time = time.time() - start_time
    print(f"{Fore.RED}{test_name}: FAILED in {elapsed_time:.2f} seconds\nError: {error}")
    return {"name": test_name, "passed": False, "total_time": elapsed_time}


def run_setup(setup_path: str) -> None:
    try:
        module = _load_module_from_path("testrium_setup_module", setup_path)
        if not hasattr(module, "main"):
            raise AttributeError(f"{setup_path} does not define main()")
        module.main()
    except Exception as exc:
        print(f"An error occurred in run_setup: {exc}")
        sys.stdout.flush()
        raise


def _load_module_from_path(module_name: str, path: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if not spec or not spec.loader:
        raise ImportError(f"Could not load module from {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _load_entrypoint(test_dir: str, entrypoint: str):
    # TODO(#24): Add decorator-declared unit entrypoints after config entrypoints stabilize.
    module_name, function_name = entrypoint.split(":", 1)
    module_path = os.path.join(test_dir, *module_name.split(".")) + ".py"

    if os.path.isfile(module_path):
        module = _load_module_from_path(
            f"testrium_entrypoint_{module_name.replace('.', '_')}",
            module_path,
        )
    else:
        sys.path.insert(0, test_dir)
        try:
            module = importlib.import_module(module_name)
        finally:
            if sys.path[0] == test_dir:
                sys.path.pop(0)

    entrypoint_fn = getattr(module, function_name, None)
    if not callable(entrypoint_fn):
        raise AttributeError(f"{entrypoint} does not resolve to a callable")
    return entrypoint_fn


def _entrypoint_worker(test_dir: str, unit_name: str, entrypoint: str, runtime_db: str):
    os.environ[EVENT_DB_ENV] = runtime_db
    os.chdir(test_dir)
    events = Events_Manager(Unit=unit_name, path=test_dir)
    try:
        entrypoint_fn = _load_entrypoint(test_dir, entrypoint)
        entrypoint_fn()
    except Exception as exc:
        events.Set_Event(
            step=f"testrium-unit-exception:{type(exc).__name__}",
            event_type="Exception",
            metadata={"message": str(exc)},
        )
        raise


def _run_single_test(test_name: str, test_func, extra_condition_fn):
    print(f"{Fore.YELLOW}Running test: {test_name}")
    start_time = time.time()

    try:
        with suppress_output():
            test_func()

        if extra_condition_fn is not None and not extra_condition_fn(test_name):
            return handle_exception(test_name, start_time, "Extra validation failed")

        elapsed_time = time.time() - start_time
        print(f"{Fore.GREEN}{test_name}: PASSED in {elapsed_time:.2f} seconds")
        return {"name": test_name, "passed": True, "total_time": elapsed_time}

    except Exception as exc:
        return handle_exception(test_name, start_time, exc)


def _ordered_test_groups(test_functions):
    tests_by_priority = {}
    for test_name, test_func in test_functions.items():
        priority = getattr(test_func, "testrium_priority", 0)
        parallelize = getattr(test_func, "testrium_parallelize", False)
        tests_by_priority.setdefault(priority, []).append(
            (test_name, test_func, parallelize)
        )

    for priority in sorted(tests_by_priority):
        yield tests_by_priority[priority]


def run_test_functions(test_functions, extra_condition_fn) -> tuple[bool, list[dict]]:
    all_tests_passed = True
    tests_completed = []

    for priority_group in _ordered_test_groups(test_functions):
        parallel_tests = [
            (test_name, test_func)
            for test_name, test_func, parallelize in priority_group
            if parallelize
        ]
        sequential_tests = [
            (test_name, test_func)
            for test_name, test_func, parallelize in priority_group
            if not parallelize
        ]

        for test_name, test_func in sequential_tests:
            result = _run_single_test(test_name, test_func, extra_condition_fn)
            tests_completed.append(result)
            all_tests_passed = all_tests_passed and result["passed"]

        if parallel_tests:
            max_workers = min(len(parallel_tests), os.cpu_count() or 1)
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures = {
                    executor.submit(
                        _run_single_test, test_name, test_func, extra_condition_fn
                    ): test_name
                    for test_name, test_func in parallel_tests
                }
                for future in as_completed(futures):
                    result = future.result()
                    tests_completed.append(result)
                    all_tests_passed = all_tests_passed and result["passed"]

    return all_tests_passed, tests_completed


def _runtime_dir(base_dir: str, dir_name: str) -> tuple[str, str]:
    safe_group = dir_name.replace(os.sep, "_").replace("/", "_")
    run_id = f"{safe_group}-{int(time.time() * 1000)}"
    path = os.path.join(base_dir, ".testrium", "runs", run_id)
    os.makedirs(path, exist_ok=True)
    return path, os.path.join(path, "Data.db")


def _terminate_process(process: Process, grace_seconds: float = 1.0) -> None:
    if not process.is_alive():
        return
    process.terminate()
    process.join(grace_seconds)
    if process.is_alive():
        process.kill()
        process.join(grace_seconds)


def _start_setup(test_dir: str, runtime_db: str) -> Process | None:
    setup_path = os.path.join(test_dir, "setup.py")
    if not os.path.exists(setup_path):
        return None

    process = Process(target=_setup_worker, args=(setup_path, runtime_db, test_dir))
    process.daemon = True
    process.start()
    return process


def _setup_worker(setup_path: str, runtime_db: str, test_dir: str) -> None:
    os.environ[EVENT_DB_ENV] = runtime_db
    os.chdir(test_dir)
    run_setup(setup_path)


def _enabled_units(units: list[dict]) -> list[dict]:
    return [unit for unit in units if unit.get("enabled", True)]


def _entrypoint_units(units: list[dict]) -> list[dict]:
    return [unit for unit in _enabled_units(units) if unit.get("entrypoint")]


def _dependencies_ready(
    unit: dict,
    statuses: UnitStatus_Manager,
    known_entrypoint_units: set[str],
) -> tuple[bool, str | None]:
    for dependency in unit.get("unit_dependencies", []):
        if dependency not in known_entrypoint_units:
            continue
        status = statuses.get_status(dependency)
        if status not in {"ready", "running", "finished", "stopped"}:
            return False, dependency
    return True, None


def run_unit_processes(
    base_dir: str,
    dir_name: str,
    units: list[dict],
    configs: dict,
    runtime_path: str,
    runtime_db: str,
) -> dict:
    start_time = time.time()
    event_manager = Events_Manager(Unit="*", path=runtime_path)
    status_manager = UnitStatus_Manager(path=runtime_path)
    unit_processes: dict[str, Process] = {}
    unit_results = []
    failures = []
    enabled_entrypoint_units = _entrypoint_units(units)

    if not enabled_entrypoint_units:
        return {
            "used_entrypoints": False,
            "passed": True,
            "duration": 0.0,
            "unit_results": [],
            "failures": [],
        }

    known_entrypoint_units = {unit["name"] for unit in enabled_entrypoint_units}
    test_dir = os.path.join(base_dir, dir_name)

    for unit in enabled_entrypoint_units:
        status_manager.set_status(unit["name"], "created")

    for unit in enabled_entrypoint_units:
        dependencies_ready, missing_dependency = _dependencies_ready(
            unit, status_manager, known_entrypoint_units
        )
        if not dependencies_ready:
            failures.append(
                {
                    "unit": unit["name"],
                    "reason": f"dependency not ready: {missing_dependency}",
                }
            )
            status_manager.set_status(unit["name"], "failed")
            break

        status_manager.set_status(unit["name"], "starting")
        process = Process(
            target=_entrypoint_worker,
            args=(test_dir, unit["name"], unit["entrypoint"], runtime_db),
        )
        process.start()
        unit_processes[unit["name"]] = process

        ready_event = unit.get("ready_event")
        if ready_event:
            ready = event_manager.wait_for_event(
                step=ready_event,
                unit=unit["name"],
                timeout=unit.get("ready_timeout", 10),
            )
            if not ready:
                failures.append(
                    {
                        "unit": unit["name"],
                        "reason": f"readiness probe timed out: {ready_event}",
                    }
                )
                status_manager.set_status(unit["name"], "failed")
                break

        status_manager.set_status(unit["name"], "ready")
        status_manager.set_status(unit["name"], "running")

    if failures:
        for process in unit_processes.values():
            _terminate_process(process)
        return {
            "used_entrypoints": True,
            "passed": False,
            "duration": time.time() - start_time,
            "unit_results": unit_results,
            "failures": failures,
        }

    group_timeout = configs.get("timeout", 30)
    deadline = time.time() + group_timeout
    entrypoint_unit_names = {unit["name"] for unit in enabled_entrypoint_units}
    monitored_units = [
        unit for unit in units if unit.get("name") in entrypoint_unit_names
    ]

    while time.time() <= deadline:
        process_failures = []
        for unit_name, process in unit_processes.items():
            if process.exitcode is not None and process.exitcode != 0:
                process_failures.append(
                    {"unit": unit_name, "reason": f"process exited {process.exitcode}"}
                )

        if process_failures:
            failures.extend(process_failures)
            break

        required = event_manager.verify_required_events(monitored_units)
        if not required["missing"]:
            break

        time.sleep(0.1)
    else:
        missing = event_manager.verify_required_events(monitored_units)["missing"]
        failures.append({"unit": "*", "reason": "required probes timed out", "missing": missing})

    passed = not failures
    for unit_name, process in unit_processes.items():
        process.join(0.5)
        if process.is_alive():
            _terminate_process(process)
            status_manager.set_status(unit_name, "stopped" if passed else "failed")
        elif process.exitcode == 0:
            status_manager.set_status(unit_name, "finished")
        else:
            status_manager.set_status(unit_name, "failed")
            passed = False

        unit_results.append(
            {
                "name": unit_name,
                "passed": status_manager.get_status(unit_name) in {"finished", "stopped"},
                "status": status_manager.get_status(unit_name),
                "exitcode": process.exitcode,
            }
        )

    return {
        "used_entrypoints": True,
        "passed": passed,
        "duration": time.time() - start_time,
        "unit_results": unit_results,
        "failures": failures,
    }


def call_tail_function(
    tests_results: list,
    events_completed: list,
    events_missing: list,
    correlations: dict,
    tail_fn: object,
):
    total_time = sum(test_result["total_time"] for test_result in tests_results)
    passed = all(test_result["passed"] for test_result in tests_results)
    data = {
        "duration": total_time,
        "passed": passed,
        "tests_results": tests_results,
        "events_completed": events_completed,
        "events_missing": events_missing,
        "correlations": correlations,
    }
    return bool(tail_fn(data))


def _print_probe_report(required: dict) -> None:
    completed = required["completed"]
    missing = required["missing"]
    for event in completed:
        print(
            f"   {Fore.GREEN}{event['unit']} completed {event['step']}"
        )
    for event in missing:
        print(
            f"   {Fore.RED}{event['unit']} missing {event['step']}"
        )


def _print_correlation_report(correlations: dict) -> None:
    # TODO(#25): Include per-pair latency details when the summary output grows a table mode.
    print(f"{Fore.BLUE}Event correlations:")
    print(f"   paired: {len(correlations['paired'])}")
    print(f"   orphan sends: {len(correlations['orphan_sends'])}")
    print(f"   orphan receives: {len(correlations['orphan_receives'])}")
    print(f"   duplicate keys: {len(correlations['duplicate_keys'])}")
    print(f"   average latency: {correlations['average_latency']:.6f}s")


def run_group(base_dir: str, dir_name: str, units: list[dict], verbose: bool) -> dict:
    group_start = time.time()
    test_dir = os.path.join(base_dir, dir_name)
    configs = load_config(os.path.join(test_dir, "config.toml"))["Configs"]
    runtime_path, runtime_db = _runtime_dir(base_dir, dir_name)
    previous_runtime_db = os.environ.get(EVENT_DB_ENV)
    os.environ[EVENT_DB_ENV] = runtime_db

    event_manager = Events_Manager(Unit="*", path=runtime_path)
    event_manager.drop_events_table()
    setup_process = None
    tests_completed = []
    all_tests_passed = True

    try:
        setup_process = _start_setup(test_dir, runtime_db)
        if setup_process:
            time.sleep(0.2)
            if setup_process.exitcode not in {None, 0}:
                raise RuntimeError(f"setup exited {setup_process.exitcode}")

        special_functions = load_special_callbakcs(test_dir)
        test_functions = load_test_functions(test_dir)

        process_result = run_unit_processes(
            base_dir=base_dir,
            dir_name=dir_name,
            units=units,
            configs=configs,
            runtime_path=runtime_path,
            runtime_db=runtime_db,
        )
        if process_result["used_entrypoints"]:
            tests_completed.append(
                {
                    "name": "unit_processes",
                    "passed": process_result["passed"],
                    "total_time": process_result["duration"],
                    "details": process_result["unit_results"],
                }
            )
            all_tests_passed = all_tests_passed and process_result["passed"]

        if test_functions:
            if not verbose:
                with suppress_output():
                    tests_ok, direct_tests = run_test_functions(
                        test_functions,
                        special_functions["validate_test"],
                    )
            else:
                tests_ok, direct_tests = run_test_functions(
                    test_functions,
                    special_functions["validate_test"],
                )
            tests_completed.extend(direct_tests)
            all_tests_passed = all_tests_passed and tests_ok

        if not tests_completed:
            tests_completed.append(
                {
                    "name": "scenario",
                    "passed": False,
                    "total_time": 0.0,
                    "reason": "no entrypoints or test functions found",
                }
            )
            all_tests_passed = False

        required = event_manager.verify_required_events(_enabled_units(units))
        correlations = event_manager.correlate_send_receive()
        all_tests_passed = all_tests_passed and not required["missing"]
        all_tests_passed = all_tests_passed and not correlations["orphan_sends"]
        all_tests_passed = all_tests_passed and not correlations["orphan_receives"]
        all_tests_passed = all_tests_passed and not correlations["duplicate_keys"]

        print(f"{Fore.BLUE}Probe report for {dir_name}:")
        _print_probe_report(required)
        _print_correlation_report(correlations)

        tail_fn = special_functions["tests_results"]
        if tail_fn is not None:
            tail_passed = call_tail_function(
                tests_completed,
                required["completed"],
                required["missing"],
                correlations,
                tail_fn,
            )
            all_tests_passed = all_tests_passed and tail_passed

        duration = time.time() - group_start
        summary = {
            "tests": tests_completed,
            "required": required,
            "correlations": correlations,
            "runtime_db": runtime_db,
        }
        if configs.get("save-metrics", True):
            Results_Manager(path=runtime_path).store_result(
                test_group=dir_name,
                passed=all_tests_passed,
                duration=duration,
                average_latency=correlations["average_latency"],
                summary=summary,
            )

        return {
            "name": dir_name,
            "passed": all_tests_passed,
            "duration": duration,
            "tests": tests_completed,
            "required": required,
            "correlations": correlations,
            "runtime_db": runtime_db,
        }
    finally:
        if setup_process is not None:
            _terminate_process(setup_process)
        if previous_runtime_db is None:
            os.environ.pop(EVENT_DB_ENV, None)
        else:
            os.environ[EVENT_DB_ENV] = previous_runtime_db


def print_summary(results: list[dict]) -> None:
    for result in results:
        print("-=" * 15)
        print(f"{Fore.CYAN}{result['name']}:")
        print(f"Elapsed time: {result['duration']:.4f}s")
        for test in result["tests"]:
            color = Fore.GREEN if test["passed"] else Fore.RED
            status = "PASS" if test["passed"] else "FAIL"
            print(f"  - {color}{status} {test['name']}")
        print(f"Runtime DB: {result['runtime_db']}")
        if result["passed"]:
            print(f"  {Fore.GREEN}All checks passed")
        else:
            print(f"  {Fore.RED}Scenario failed")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Testrium CLI")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show logs")
    parser.add_argument(
        "--less",
        nargs="+",
        type=str,
        help="List of specific test group names to exclude",
    )
    subparsers = parser.add_subparsers(dest="command", help="Sub-command help")
    subparsers.add_parser("run", help="Run the tests")

    benchmark_parser = subparsers.add_parser(
        "benchmark",
        help="Collect machine benchmark scores for result normalization",
    )
    benchmark_parser.add_argument(
        "--database",
        default=None,
        help="Optional SQLite database path to store the benchmark result",
    )
    benchmark_parser.add_argument(
        "--iterations",
        type=int,
        default=3,
        help="Number of iterations for each benchmark sample",
    )

    gen_configs_parser = subparsers.add_parser(
        "gen-configs",
        help="Generate config.toml and unit templates in a target directory",
    )
    gen_configs_parser.add_argument(
        "gen_path",
        nargs="?",
        default=".",
        help='Path for generation. Use "." for the current directory',
    )

    gen_parser = subparsers.add_parser("gen", help="Generate templates")
    gen_parser.add_argument(
        "type", choices=["config-template"], help="Type of template to generate"
    )
    gen_parser.add_argument(
        "gen_path",
        nargs="?",
        default=".",
        help="Optional path for generation",
    )
    return parser


def run_cli(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "gen":
        resolve_template(args.type, args.gen_path)
        return EXIT_SUCCESS

    if args.command == "gen-configs":
        resolve_template("config-template", args.gen_path)
        return EXIT_SUCCESS

    if args.command == "benchmark":
        result = run_machine_benchmark(iterations=args.iterations)
        if args.database:
            save_benchmark_result(args.database, result)
        print(result.to_dict())
        return EXIT_SUCCESS

    if args.command not in {None, "run"}:
        parser.print_help()
        return EXIT_CONFIG_ERROR

    base_dir = os.getcwd()
    exclude_tests = args.less or []

    if args.verbose:
        print("Verbose mode enabled")
    if exclude_tests:
        print("Base Directory:", base_dir)
        print("Excluded Tests:", exclude_tests)

    print(f"{Fore.GREEN}Current working directory: {base_dir}")
    try:
        valid_tests = discover_tests(base_dir, exclude_tests)
    except ValueError as exc:
        print(f"{Fore.RED}Configuration error: {exc}")
        return EXIT_CONFIG_ERROR

    if not valid_tests:
        print(f"{Fore.RED}No valid test groups found")
        return EXIT_NO_TESTS

    print(f"{Fore.GREEN}Found {len(valid_tests)} valid test groups")
    for dir_name, units in valid_tests:
        print(f"{Fore.GREEN} - {dir_name}")
        for unit in units:
            if unit.get("enabled", True):
                print(f"   {Fore.GREEN} - Unit {unit['name']}")
            else:
                print(f"   {Fore.BLUE} - Unit {unit['name']} disabled")

    results = []
    for dir_name, units in valid_tests:
        try:
            result = run_group(base_dir, dir_name, units, args.verbose)
            results.append(result)
            print_banner(" PASS " if result["passed"] else " FAILURE ", Fore.GREEN if result["passed"] else Fore.RED)
        except ValueError as exc:
            print(f"{Fore.RED}{dir_name}: configuration error: {exc}")
            return EXIT_CONFIG_ERROR
        except Exception as exc:
            print(f"{Fore.RED}{dir_name}: failed: {exc}")
            results.append(
                {
                    "name": dir_name,
                    "passed": False,
                    "duration": 0.0,
                    "tests": [],
                    "required": {"completed": [], "missing": []},
                    "correlations": {},
                    "runtime_db": "",
                }
            )

    print_summary(results)
    return EXIT_SUCCESS if all(result["passed"] for result in results) else EXIT_FAILURE


def main():
    sys.exit(run_cli())


if __name__ == "__main__":
    main()
