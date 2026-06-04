import os
from posixpath import dirname
import time
import importlib.util
import argparse
import toml
from colorama import init, Fore, Style
from .modules.events import Events_Manager
from .common.loaders import (
    load_config,
    load_special_callbakcs,
    load_test_functions,
    discover_tests,
)
from .common.utils import print_banner, suppress_output
import pandas as pd
from multiprocessing import Process, Event, Manager
import sys
from testrium.common.generator.main import resolve_template
from concurrent.futures import ThreadPoolExecutor, as_completed
from testrium.tools.benchmark import run_machine_benchmark, save_benchmark_result

# Initialize colorama
init(autoreset=True)


# Extra validation step that user migh want to define
def dummy_function():
    """
    - This will allow to define a extra step in the verification
    for example, read a file and validate if the test was a success.
    see if the code did what it was suposed to do. etc..
    """
    pass


def run_setup(setup_path):
    try:
        print(setup_path)
        sys.stdout.flush()  # Ensure the output is flushed immediately
        module_name = "setup_module"
        spec = importlib.util.spec_from_file_location(module_name, setup_path)
        if spec and spec.loader:
            setup_module = importlib.util.module_from_spec(spec)
            sys.modules[module_name] = setup_module
            spec.loader.exec_module(setup_module)
            setup_module.main()
        else:
            print(f"Could not load module from {setup_path}")
            sys.stdout.flush()  # Ensure the output is flushed immediately
    except Exception as e:
        print(f"An error occurred in run_setup: {e}")
        sys.stdout.flush()  # Ensure the output is flushed immediately


# t1 = Process(target=self.initializer, args=())
# t2 = Process(target=senders.send_some_data, args=())
# t3 = Process(target=self.monitor_stop_event, args=())
#
# t1.start()
# time.sleep(5)
# t2.start()
# t3.start()
#
# t3.join()
#
# time.sleep(5)
#
# # PID is the process ID of the process you want to send the signal to.
# # You would typically get this from the 'pid' attribute of a process.
# os.kill(t1.pid, signal.SIGINT)
#
# t1.join()  # Wait for the process to finish
# t2.join()


def handle_exception(test_name: str, start_time, e: str) -> dict:
    elapsed_time = time.time() - start_time
    print(f"{Fore.RED}{test_name}: FAILED in {elapsed_time:.2f} seconds\nError: {e}")
    return {"name": test_name, "passed": False, "total_time": elapsed_time}


def _run_single_test(test_name: str, test_func, extra_condition_fn):
    print(f"{Fore.YELLOW}Running test: {test_name}")
    start_time = time.time()

    try:
        if test_name == "log_test_time":
            pass
        elif test_name == "verify_condition":
            with suppress_output():
                test_func(lambda: True)
        else:
            with suppress_output():
                test_func()

        if extra_condition_fn is not None and not extra_condition_fn(test_name):
            return handle_exception(test_name, start_time, "Extra validation failed")

        elapsed_time = time.time() - start_time
        print(f"{Fore.GREEN}{test_name}: PASSED in {elapsed_time:.2f} seconds")
        return {"name": test_name, "passed": True, "total_time": elapsed_time}

    except Exception as e:
        return handle_exception(test_name, start_time, e)


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


def run_test(base_dir: str, dir_name: str, test_functions, extra_condition_fn):
    """
    This method load the test functions and the special functions,
    the test function is the test that will run and the special function
    is a extra verification that can be added to run in the end.

    This functions will return:
    - all_tests_passed: boolean
    - test_complete: list

    The test complete is a list of this:

    ```python
    {"name":test_name, "passed":True, "total_time":elapsed_time}
    ```

    This dictionary list contain basically the resume of each test completed
    """

    Events_Manager(Unit="", path=base_dir).drop_events_table()

    setup_path = os.path.join(base_dir, dir_name, "setup.py")

    if os.path.exists(setup_path):
        t1 = Process(target=run_setup, args=(setup_path,))
        t1.daemon = True  # Set the process as a daemon
        t1.start()
        # run_setup(setup_path)
        time.sleep(1)

    # TODO >>> Use the units order to setup the units one by one
    # TODO >>> Create a meachanism to verify the events when they are required

    print(f"{Fore.BLUE}Loading tests for {dir_name}...")

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

    if os.path.exists(setup_path):
        t1.kill()

    # -> Handle the case where the setup fails and none of the tests has the change to run
    if len(tests_completed) == 0:
        for test_name, test_func in test_functions.items():
            tests_completed.append(
                handle_exception(
                    test_name, time.time(), "Setup so all tests was skipped"
                )
            )

    return all_tests_passed, tests_completed


def call_tail_function(
    tests_results: list, events_completed: list, events_missing: list, tail_fn: object
):
    """
    This method call the function that will receive the score and information of the test in the end.
    you can use this to make a last verification step that can influentiate if the test passed or not,
    by return True or False in the end you can fail the test if you want to or send back True, that will
    not fail the test if if was not failed before.
    """

    # > Verify if all fail or passed, and calc test total time to run.
    total_time = 0
    passed = True
    for test_result in tests_results:
        total_time += test_result["total_time"]
        if not test_result["passed"]:
            passed = False
        else:
            continue

    data = {
        "duration": total_time,
        "passed": passed,
        "tests_results": tests_results,
        "events_completed": events_completed,
        "events_missing": events_missing,
    }

    if tail_fn(data):  # If response == False, test will fail
        pass
    else:
        return False

    return True


def main():
    parser = argparse.ArgumentParser(description='Testrium CLI')
    parser.add_argument('-v', '--verbose', action='store_true', help='Show logs')
    parser.add_argument('--less', nargs='+', type=str, help='List of specific test names to exclude')
    subparsers = parser.add_subparsers(dest='command', help='Sub-command help')
    run_parser = subparsers.add_parser('run', help='Run the tests')

    benchmark_parser = subparsers.add_parser(
        'benchmark',
        help='Collect machine benchmark scores for result normalization',
    )
    benchmark_parser.add_argument(
        '--database',
        default=None,
        help='Optional SQLite database path to store the benchmark result',
    )
    benchmark_parser.add_argument(
        '--iterations',
        type=int,
        default=3,
        help='Number of iterations for each benchmark sample',
    )

    gen_configs_parser = subparsers.add_parser(
        'gen-configs',
        help='Generate config.toml and units templates in a target directory',
    )
    gen_configs_parser.add_argument(
        'gen_path',
        nargs='?',
        default='.',
        help='Path for generation. Use "." for the current directory',
    )

    gen_parser = subparsers.add_parser('gen', help='Generate already made templates')
    gen_parser.add_argument('type', choices=["config-template"], help='Type of the template to generate')
    gen_parser.add_argument(
        'gen_path',
        nargs='?',
        default='.',
        help='Optional path for the generation',
    )
    args = parser.parse_args()

    if args.command == "gen":
        resolve_template(args.type, args.gen_path)
        return

    if args.command == "gen-configs":
        resolve_template("config-template", args.gen_path)
        return

    if args.command == "benchmark":
        result = run_machine_benchmark(iterations=args.iterations)
        if args.database:
            save_benchmark_result(args.database, result)
        print(result.to_dict())
        return
    
    base_dir = os.getcwd()

    exclude_tests = []
        # Handle --less option
    if args.less:
        exclude_tests.extend(args.less)
        print("Base Directory:", base_dir)
        print("Excluded Tests:", args.less)

    # Verbose mode
    if args.verbose:
        print("Verbose mode enabled")
        
    print(f"{Fore.GREEN}Current working directory: {base_dir}")

    valid_tests = discover_tests(base_dir, exclude_tests)

    # -> Early retun if not find any test:
    tests_finded = len(valid_tests)
    if tests_finded > 0:
        print(f"{Fore.GREEN} Find: {tests_finded:.0f} valid test groups!")
        for test_group in valid_tests:
            print(f"{Fore.GREEN} - {test_group[0]}")
            for unit in test_group[1]:
                print(f"   {Fore.GREEN} - Unit {unit['name']}")
    else:
        print(f"{Fore.RED} No valid test groups finded!")
        return

    # TODO >>> Find a way to log the milestones completed for each test and with this understand what they relate to

    tests_passed = {}

    # -> Run the valid tests:
    for dir_name, units in valid_tests:
        # TODO >>> Enhance the config loading to have a structure verification
        # TODO >>> Add option to disble a test if want to using somehting like enable: False for example

        # > Load test configs
        configs = load_config(os.path.join(dir_name, "config.toml"))

        # > Load Units
        confs = configs["Configs"]

        # > Load Units Predefinitions
        total_units = 0
        units_index = {}

        # TODO >>> Validate index of units, avoid duplicates - beqm
        for unit in units:
            units_index[unit["init"]] = {"name": f"{unit['name']}", "events": f"{unit['events']}"}
            total_units += 1

        print(f"Units loaded: {units_index}")

        dir_path = os.path.join(base_dir, dir_name)

        test_functions = load_test_functions(dir_path)
        special_functions = load_special_callbakcs(dir_path)

        # > Run extra validation
        extra_condition_fn = special_functions["validate_test"]
        if not args.verbose:
            with suppress_output():
                all_tests_passed, tests_passed[f"{dir_name}"] = run_test(
                    base_dir, dir_name, test_functions, extra_condition_fn
                )
        else:
            all_tests_passed, tests_passed[f"{dir_name}"] = run_test(
                base_dir, dir_name, test_functions, extra_condition_fn
            )        

        events_completed = []
        events_missing = []

        # > Verify Events Completed By The Unit
        for i in range(total_units):
            unit = units_index[i]
            unit_name = unit["name"]
            if unit_name == "":
                continue

            unit_events = (
                pd.DataFrame.from_dict(
                    Events_Manager(Unit=unit_name, path=base_dir).List_Events()
                )
                .loc[:, "StepCompleted"]
                .to_list()
            )

            print(f"{Fore.BLUE} Unit {unit['name']}")
            for event in unit["events"]:
                if event not in unit_events:
                    print(f"   - {Fore.RED}{event} was not completed!")
                    events_missing.append(event)
                    all_tests_passed = False
                else:
                    print(f"   - {Fore.GREEN}{event} was sucessfully completed!")
                    events_completed.append(event)
                    continue

        # > Call the tail callback
        tail_fn = special_functions["tests_results"]
        if tail_fn != None:
            if not call_tail_function(
                tests_passed[f"{dir_name}"], events_completed, events_missing, tail_fn
            ):
                print(f"❗{Fore.RED}Tail Function Fail")
                all_tests_passed = False
        else:
            pass

        if all_tests_passed:
            print_banner(" PASS ", Fore.GREEN)
        else:
            print_banner(" FAILURE ", Fore.RED)

    # -> SHOW RESUME ON SCREEN:
    for name, tests in tests_passed.items():
        print("-=" * 15)
        print(f"{Fore.CYAN}{name}:")
        all_p = True
        total_time = 0

        passed = 0
        for test in tests:
            all_s_p = True
            total_time += test["total_time"]
            if test["passed"]:
                passed += 1
                continue
            else:
                all_s_p = False

        print(f"⚡ Elapsed time: {total_time}")
        if not all_s_p:
            print(f"{Fore.RED}{passed}/{len(tests)} Passed!")
        else:
            print(f"{Fore.GREEN}{passed}/{len(tests)} Passed!")

        for test in tests:
            if test["passed"]:
                print(f"  - ✅ {Fore.GREEN}{test['name']}")
            else:
                print(f"  - 🟥 {Fore.RED}{test['name']}")
                all_p = False

        if all_p:
            print(f"  🚀 {Fore.GREEN}All Tests Passed!")
        else:
            print(f"  💥 {Fore.RED}FAIL!")


if __name__ == "__main__":
    main()
