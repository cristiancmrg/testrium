import pytest

from testrium.common.validate_configs import (
    normalize_config,
    normalize_unit_config,
    validate_unit_collection,
)


def test_normalize_config_accepts_legacy_metric_keys():
    config = normalize_config(
        {
            "Configs": {
                "units": ["target", "source"],
                "analitics": True,
                "save-analitics": True,
                "save-performance": False,
            }
        }
    )

    assert config["Configs"]["gen-metrics"] is True
    assert config["Configs"]["save-metrics"] is True
    assert config["Configs"]["save-scores"] is False


def test_normalize_config_rejects_duplicate_units():
    with pytest.raises(ValueError, match="duplicate values"):
        normalize_config({"Configs": {"units": ["source", "source"]}})


def test_unit_entrypoint_requires_module_function_format():
    with pytest.raises(ValueError, match="module:function"):
        normalize_unit_config(
            {
                "init": 0,
                "events": ["target-ready"],
                "entrypoint": "run_target",
            },
            "target",
        )


def test_unit_collection_rejects_duplicate_init():
    units = [
        {"name": "target", "init": 0, "enabled": True, "unit_dependencies": []},
        {"name": "source", "init": 0, "enabled": True, "unit_dependencies": []},
    ]

    with pytest.raises(ValueError, match="duplicate unit init"):
        validate_unit_collection(units, ["target", "source"])


def test_unit_collection_rejects_unknown_dependency():
    units = [
        {
            "name": "source",
            "init": 0,
            "enabled": True,
            "unit_dependencies": ["missing"],
        }
    ]

    with pytest.raises(ValueError, match="unknown unit"):
        validate_unit_collection(units, ["source"])
