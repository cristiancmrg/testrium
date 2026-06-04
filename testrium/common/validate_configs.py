VALID_DEBUG_MODES = {"DEBUG", "INFO", "WARNING", "EXCEPT"}
VALID_IN_EXCEPT = {"Resume", "Reload", "Resume-ALL"}

CONFIG_DEFAULTS = {
    "enabled": True,
    "units": [],
    "debug-modes": ["DEBUG", "INFO", "WARNING", "EXCEPT"],
    "test-modes": ["DEBUG"],
    "repeat": 0,
    "timeout": 30,
    "use-ai": False,
    "diagnostics": True,
    "detect-bad-behavior": True,
    "save-resume": True,
    "gen-metrics": True,
    "save-metrics": True,
    "save-scores": True,
}

LEGACY_CONFIG_KEYS = {
    "analitics": "gen-metrics",
    "save-analitics": "save-metrics",
    "save-performance": "save-scores",
}

UNIT_DEFAULTS = {
    "enabled": True,
    # TODO(#24): Decorator-based entrypoints should normalize into this field.
    "entrypoint": None,
    "ready_event": None,
    "ready_timeout": 10,
    "timeout": None,
    "use_setup": False,
    "in-except": "Resume",
    "unit_dependencies": [],
}

LEGACY_UNIT_KEYS = {
    "unity_depencies": "unit_dependencies",
}


def _copy_with_aliases(config: dict, aliases: dict) -> dict:
    normalized = dict(config)
    for old_key, new_key in aliases.items():
        if old_key in normalized and new_key not in normalized:
            normalized[new_key] = normalized[old_key]
    return normalized


def _validate_string_list(value, field_name: str, required: bool = True) -> list[str]:
    if value is None and not required:
        return []
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"{field_name} must be a list of strings")
    if any(not item.strip() for item in value):
        raise ValueError(f"{field_name} cannot contain blank values")
    return value


def _ensure_unique_strings(values: list[str], field_name: str) -> None:
    seen = set()
    duplicates = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    if duplicates:
        raise ValueError(
            f"{field_name} contains duplicate values: "
            + ", ".join(sorted(duplicates))
        )


def _validate_optional_string(value, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value


def _validate_bool(value, field_name: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field_name} must be a boolean")
    return value


def _validate_timeout(value, field_name: str, required: bool = True) -> int | float | None:
    if value is None and not required:
        return None
    if not isinstance(value, (int, float)) or value <= 0:
        raise ValueError(f"{field_name} must be a positive number")
    return value


def _validate_entrypoint(value: str | None) -> str | None:
    entrypoint = _validate_optional_string(value, "unit entrypoint")
    if entrypoint is None:
        return None
    if ":" not in entrypoint:
        raise ValueError('unit entrypoint must use "module:function" format')
    module_name, function_name = entrypoint.split(":", 1)
    if not module_name.strip() or not function_name.strip():
        raise ValueError('unit entrypoint must use "module:function" format')
    return entrypoint


def normalize_config(config: dict) -> dict:
    if not isinstance(config, dict):
        raise ValueError("config.toml must load into a dictionary")

    if "Configs" not in config or not isinstance(config["Configs"], dict):
        raise ValueError('config.toml must contain a ["Configs"] table')

    configs = _copy_with_aliases(config["Configs"], LEGACY_CONFIG_KEYS)
    normalized_configs = {**CONFIG_DEFAULTS, **configs}

    units = _validate_string_list(normalized_configs.get("units"), "Configs.units")
    _ensure_unique_strings(units, "Configs.units")
    debug_modes = _validate_string_list(
        normalized_configs.get("debug-modes"), "Configs.debug-modes"
    )

    invalid_debug_modes = set(debug_modes) - VALID_DEBUG_MODES
    if invalid_debug_modes:
        raise ValueError(
            "Configs.debug-modes contains invalid modes: "
            + ", ".join(sorted(invalid_debug_modes))
        )

    test_modes = normalized_configs.get("test-modes")
    if isinstance(test_modes, str):
        if test_modes != "All" and test_modes not in VALID_DEBUG_MODES:
            raise ValueError("Configs.test-modes contains an invalid mode")
    else:
        invalid_test_modes = set(
            _validate_string_list(test_modes, "Configs.test-modes")
        ) - VALID_DEBUG_MODES
        if invalid_test_modes:
            raise ValueError(
                "Configs.test-modes contains invalid modes: "
                + ", ".join(sorted(invalid_test_modes))
            )

    repeat = normalized_configs.get("repeat")
    if not isinstance(repeat, int) or repeat < 0 or repeat > 10:
        raise ValueError("Configs.repeat must be an integer between 0 and 10")

    _validate_bool(normalized_configs.get("enabled"), "Configs.enabled")
    _validate_timeout(normalized_configs.get("timeout"), "Configs.timeout")

    for field_name in (
        "use-ai",
        "diagnostics",
        "detect-bad-behavior",
        "save-resume",
        "gen-metrics",
        "save-metrics",
        "save-scores",
    ):
        _validate_bool(normalized_configs.get(field_name), f"Configs.{field_name}")

    normalized = dict(config)
    normalized["Configs"] = normalized_configs
    normalized["Configs"]["units"] = units
    return normalized


def normalize_unit_config(config: dict, unit_name: str | None = None) -> dict:
    if not isinstance(config, dict):
        raise ValueError("unit config must load into a dictionary")

    unit_config = _copy_with_aliases(config, LEGACY_UNIT_KEYS)
    unit_config = {**UNIT_DEFAULTS, **unit_config}

    init = unit_config.get("init")
    if not isinstance(init, int) or init < 0:
        raise ValueError("unit init must be a non-negative integer")

    events = _validate_string_list(unit_config.get("events"), "unit events")
    _ensure_unique_strings(events, "unit events")
    unit_config["events"] = events
    unit_config["entrypoint"] = _validate_entrypoint(unit_config.get("entrypoint"))
    unit_config["ready_event"] = _validate_optional_string(
        unit_config.get("ready_event"), "unit ready_event"
    )
    unit_config["ready_timeout"] = _validate_timeout(
        unit_config.get("ready_timeout"), "unit ready_timeout"
    )
    unit_config["timeout"] = _validate_timeout(
        unit_config.get("timeout"), "unit timeout", required=False
    )
    unit_config["enabled"] = _validate_bool(unit_config.get("enabled"), "unit enabled")

    in_except = unit_config.get("in-except")
    if in_except not in VALID_IN_EXCEPT:
        raise ValueError(
            "unit in-except must be one of: " + ", ".join(sorted(VALID_IN_EXCEPT))
        )

    unit_config["use_setup"] = _validate_bool(
        unit_config.get("use_setup"), "unit use_setup"
    )

    unit_dependencies = _validate_string_list(
        unit_config.get("unit_dependencies"), "unit unit_dependencies", required=False
    )
    _ensure_unique_strings(unit_dependencies, "unit unit_dependencies")
    unit_config["unit_dependencies"] = unit_dependencies

    if unit_name is not None:
        unit_config["name"] = unit_name

    return unit_config


def validate_unit_collection(units: list[dict], configured_units: list[str]) -> None:
    loaded_names = [unit["name"] for unit in units]
    if set(loaded_names) != set(configured_units):
        missing = set(configured_units) - set(loaded_names)
        extra = set(loaded_names) - set(configured_units)
        details = []
        if missing:
            details.append("missing: " + ", ".join(sorted(missing)))
        if extra:
            details.append("extra: " + ", ".join(sorted(extra)))
        raise ValueError("unit config mismatch (" + "; ".join(details) + ")")

    init_indexes: dict[int, str] = {}
    for unit in units:
        init = unit["init"]
        if init in init_indexes:
            raise ValueError(
                f"duplicate unit init index {init}: {init_indexes[init]} and {unit['name']}"
            )
        init_indexes[init] = unit["name"]

    enabled_names = {unit["name"] for unit in units if unit.get("enabled", True)}
    all_names = set(loaded_names)
    for unit in units:
        for dependency in unit.get("unit_dependencies", []):
            if dependency not in all_names:
                raise ValueError(
                    f"unit {unit['name']} depends on unknown unit {dependency}"
                )
            if unit.get("enabled", True) and dependency not in enabled_names:
                raise ValueError(
                    f"unit {unit['name']} depends on disabled unit {dependency}"
                )


def validate_config(config: dict) -> bool:
    try:
        normalize_config(config)
        return True
    except ValueError:
        return False


def validate_unit(config: dict) -> bool:
    try:
        normalize_unit_config(config)
        return True
    except ValueError:
        return False
