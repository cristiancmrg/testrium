VALID_DEBUG_MODES = {"DEBUG", "INFO", "WARNING", "EXCEPT"}
VALID_IN_EXCEPT = {"Resume", "Reload", "Resume-ALL"}

CONFIG_DEFAULTS = {
    "units": [],
    "debug-modes": ["DEBUG", "INFO", "WARNING", "EXCEPT"],
    "test-modes": ["DEBUG"],
    "repeat": 0,
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
    return value


def normalize_config(config: dict) -> dict:
    if not isinstance(config, dict):
        raise ValueError("config.toml must load into a dictionary")

    if "Configs" not in config or not isinstance(config["Configs"], dict):
        raise ValueError('config.toml must contain a ["Configs"] table')

    configs = _copy_with_aliases(config["Configs"], LEGACY_CONFIG_KEYS)
    normalized_configs = {**CONFIG_DEFAULTS, **configs}

    units = _validate_string_list(normalized_configs.get("units"), "Configs.units")
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

    for field_name in (
        "use-ai",
        "diagnostics",
        "detect-bad-behavior",
        "save-resume",
        "gen-metrics",
        "save-metrics",
        "save-scores",
    ):
        if not isinstance(normalized_configs.get(field_name), bool):
            raise ValueError(f"Configs.{field_name} must be a boolean")

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

    _validate_string_list(unit_config.get("events"), "unit events")

    in_except = unit_config.get("in-except")
    if in_except not in VALID_IN_EXCEPT:
        raise ValueError(
            "unit in-except must be one of: " + ", ".join(sorted(VALID_IN_EXCEPT))
        )

    if not isinstance(unit_config.get("use_setup"), bool):
        raise ValueError("unit use_setup must be a boolean")

    _validate_string_list(
        unit_config.get("unit_dependencies"), "unit unit_dependencies", required=False
    )

    if unit_name is not None:
        unit_config["name"] = unit_name

    return unit_config


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
