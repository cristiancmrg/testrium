import time
import contextlib
import os
import sys
from colorama import Fore
import shutil


def log_test_time(func):
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        elapsed_time = time.time() - start_time
        print(f"{func.__name__} took {elapsed_time:.2f} seconds")
        return result

    return wrapper


def test_config(priority: int = 0, parallelize: bool = False):
    def decorator(func):
        func.testrium_priority = priority
        func.testrium_parallelize = parallelize
        return func

    return decorator


def verify_condition(condition, message="Verification failed"):
    if not condition:
        raise AssertionError(message)


@contextlib.contextmanager
def suppress_output():
    with open(os.devnull, "w") as devnull:
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        sys.stdout = devnull
        sys.stderr = devnull
        try:
            yield
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr


# Print the nice Pass or Fail banners
def print_banner(message, color=Fore.GREEN):
    term_width = shutil.get_terminal_size().columns
    message_length = len(message)
    padding_length = (term_width - message_length) // 2
    banner = "=" * padding_length + message + "=" * padding_length

    # Ensure the banner fits exactly in the terminal width
    if len(banner) < term_width:
        banner += "=" * (term_width - len(banner))

    print(color + banner)
