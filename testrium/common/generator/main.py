import os
import shutil
from colorama import Fore


def resolve_generation_path(path: str | None) -> str:
    target_path = path or "."
    return os.path.abspath(os.path.expanduser(target_path))


def _copy_template_file(source: str, destination: str) -> None:
    destination_file = os.path.join(destination, os.path.basename(source))
    if os.path.isfile(destination_file):
        print(f"{Fore.BLUE} {os.path.basename(source)} already exists")
        return
    shutil.copy2(source, destination)


def resolve_template(type: str, path: str | None = "."):
    if type == "config-template":
        target_path = resolve_generation_path(path)
        if not os.path.isdir(target_path):
            print(f"{Fore.RED} path argument is invalid")
            return

        template_dir = os.path.dirname(__file__)
        _copy_template_file(os.path.join(template_dir, "config.toml"), target_path)
        _copy_template_file(os.path.join(template_dir, "test_case.py"), target_path)

        units_source = os.path.join(template_dir, "units")
        units_target = os.path.join(target_path, "units")
        os.makedirs(units_target, exist_ok=True)
        for filename in os.listdir(units_source):
            if filename.endswith(".toml"):
                _copy_template_file(os.path.join(units_source, filename), units_target)

        print(f"{Fore.GREEN} config template generated in {target_path}")

