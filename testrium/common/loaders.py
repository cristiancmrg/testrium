# Loads the config for each test:
import os
import importlib.util
import toml
from colorama import Fore
from .validate_configs import (
    normalize_config,
    normalize_unit_config,
    validate_unit_collection,
)


def load_config(config_path):
    print(f"{Fore.CYAN}Loading config from {config_path}")
    with open(config_path, "r") as file:
        config = toml.load(file)
    return normalize_config(config)


# Loads the test functions:
def load_test_functions(dir_path):
    test_functions = {}
    for filename in os.listdir(dir_path):
        if filename.startswith("_") or not filename.endswith(".py"):
            continue
        if filename == "setup.py":
            continue

        module_name = filename[:-3]
        file_path = os.path.join(dir_path, filename)
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        for attr in dir(module):
            if not attr.startswith("test_"):
                continue
            if attr in {"test_config", "tests_results"}:
                continue
            if attr == "test_results":
                continue

            func = getattr(module, attr)
            if callable(func) and not attr.startswith("_"):
                test_functions[attr] = func

    return test_functions


def load_special_callbakcs(dir_path):
    """
    This method is used to load the special functions that are:
    - test_validation
    - test_results_handler

    This helper callbacks allows more dinamic patterns to emerge
    """

    def get_fn(module, attr):
        func = getattr(module, attr)
        if callable(func) and not attr.startswith("_"):
            return func

    special_callbacks = {
        "validate_test": None,
        "tests_results": None,
    }

    for filename in os.listdir(dir_path):
        if filename.startswith("_") or not filename.endswith(".py"):
            continue
        module_name = filename[:-3]
        file_path = os.path.join(dir_path, filename)
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        for attr in dir(module):
            if attr == "validate_test":
                special_callbacks[attr] = get_fn(module, attr)

            elif attr == "tests_results":
                special_callbacks[attr] = get_fn(module, attr)

            else:
                continue

    return special_callbacks


def discover_tests(base_dir: str, exclude_tests: list, strict: bool = True):
    dir_names = os.listdir(base_dir)
    valid_tests = []

    # -> Discover valid test folders with configs inside
    for dir_name in dir_names:
        if dir_name in exclude_tests:
            print(f"Excluded test directory: {dir_name}")
            continue

        dir_path = os.path.join(base_dir, dir_name)

        if not os.path.isdir(dir_path):
            continue

        if "test" not in dir_name:
            continue

        config_path = os.path.join(dir_path, "config.toml")
        unit_path = os.path.join(dir_path, "units")

        if not os.path.isdir(unit_path):
            continue

        if not os.path.exists(config_path):
            print(f"{Fore.RED} File: {dir_name} invalid test")
            if strict:
                raise ValueError(f"{dir_name} is missing config.toml")
            continue

        try:
            group_config = load_config(config_path)
            if not group_config["Configs"].get("enabled", True):
                print(f"{Fore.BLUE}Skipped disabled test group: {dir_name}")
                continue
            units = resolve_units(unit_path, config_path)
        except ValueError as exc:
            print(f"{Fore.RED} File: {dir_name} invalid config: {exc}")
            if strict:
                raise ValueError(f"{dir_name}: {exc}") from exc
            continue

        print(f"{Fore.MAGENTA}Found unit directory: {dir_name}")
        valid_tests.append((dir_name, units))

    return valid_tests


def resolve_units(path: str, config_path):
    units = []
    config = load_config(config_path)
    configured_units = config["Configs"]["units"]

    for file in os.listdir(path):
        if not file.endswith(".toml"):
            continue

        filename = file.replace(".toml", "")
        if filename not in configured_units:
            continue

        unit_path = os.path.join(path, file)
        raw_unit_file = toml.load(unit_path)
        if filename not in raw_unit_file:
            print(f" {Fore.RED}{file} does not contain a [{filename}] table")
            continue
        try:
            unit_config = normalize_unit_config(raw_unit_file[filename], filename)
        except ValueError as exc:
            print(f" {Fore.RED}{file} is invalid: {exc}")
            continue
        print(f" {Fore.GREEN}{file} is valid")
        units.append(unit_config)

    loaded_units = {unit["name"] for unit in units}
    missing_units = set(configured_units) - loaded_units
    if missing_units:
        raise ValueError(
            "missing unit config files for: " + ", ".join(sorted(missing_units))
        )

    validate_unit_collection(units, configured_units)
    return sorted(units, key=lambda unit: unit["init"])
