import hashlib
import os
import platform
import sqlite3
import statistics
import tempfile
import time
from dataclasses import dataclass, asdict
from typing import Callable


@dataclass
class BenchmarkResult:
    machine_id: str
    cpu_score: float
    memory_score: float
    disk_score: float
    io_score: float
    score: float

    def to_dict(self) -> dict:
        return asdict(self)


def get_machine_id() -> str:
    identity = "|".join(
        [
            platform.node(),
            platform.system(),
            platform.machine(),
            platform.processor(),
        ]
    )
    return hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]


def _time_operation(operation: Callable[[], None], iterations: int) -> float:
    if iterations < 1:
        raise ValueError("iterations must be greater than zero")
    samples = []
    for _ in range(iterations):
        start_time = time.perf_counter()
        operation()
        samples.append(time.perf_counter() - start_time)
    return statistics.median(samples)


def _score_from_seconds(seconds: float) -> float:
    if seconds <= 0:
        return 0.0
    return 1.0 / seconds


def cpu_benchmark(iterations: int = 3) -> float:
    def operation():
        result = 0.0
        for value in range(1, 100000):
            result += (value ** 0.5) ** 2
        return result

    return _score_from_seconds(_time_operation(operation, iterations))


def memory_benchmark(iterations: int = 3) -> float:
    def operation():
        values = list(range(100000))
        sum(values)

    return _score_from_seconds(_time_operation(operation, iterations))


def disk_benchmark(iterations: int = 3, size_kb: int = 256) -> float:
    data = os.urandom(size_kb * 1024)

    def operation():
        with tempfile.NamedTemporaryFile(delete=False) as temp_file:
            temp_file.write(data)
            temp_file.flush()
            os.fsync(temp_file.fileno())
            temp_path = temp_file.name
        with open(temp_path, "rb") as temp_file:
            temp_file.read()
        os.remove(temp_path)

    return _score_from_seconds(_time_operation(operation, iterations))


def io_benchmark(iterations: int = 3, lines: int = 5000) -> float:
    def operation():
        with tempfile.NamedTemporaryFile("w", delete=False) as temp_file:
            for _ in range(lines):
                temp_file.write("This is a test.\n")
            temp_path = temp_file.name
        os.remove(temp_path)

    return _score_from_seconds(_time_operation(operation, iterations))


def calculate_machine_score(
    cpu_score: float,
    memory_score: float,
    disk_score: float,
    io_score: float,
) -> float:
    scores = [cpu_score, memory_score, disk_score, io_score]
    return statistics.geometric_mean(score for score in scores if score > 0)


def run_machine_benchmark(machine_id: str | None = None, iterations: int = 3) -> BenchmarkResult:
    cpu_score = cpu_benchmark(iterations)
    memory_score = memory_benchmark(iterations)
    disk_score = disk_benchmark(iterations)
    io_score = io_benchmark(iterations)
    score = calculate_machine_score(cpu_score, memory_score, disk_score, io_score)
    return BenchmarkResult(
        machine_id=machine_id or get_machine_id(),
        cpu_score=cpu_score,
        memory_score=memory_score,
        disk_score=disk_score,
        io_score=io_score,
        score=score,
    )


def normalize_duration(duration: float, machine_score: float, baseline_score: float) -> float:
    if duration < 0:
        raise ValueError("duration must be greater than or equal to zero")
    if machine_score <= 0 or baseline_score <= 0:
        raise ValueError("machine_score and baseline_score must be greater than zero")
    return duration * (machine_score / baseline_score)


def save_benchmark_result(database_path: str, result: BenchmarkResult) -> None:
    conn = sqlite3.connect(database_path)
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS benchmark_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                machine_id TEXT,
                cpu_score REAL,
                memory_score REAL,
                disk_score REAL,
                io_score REAL,
                score REAL,
                created_at REAL
            )
            """
        )
        cursor.execute(
            """
            INSERT INTO benchmark_results (
                machine_id,
                cpu_score,
                memory_score,
                disk_score,
                io_score,
                score,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                result.machine_id,
                result.cpu_score,
                result.memory_score,
                result.disk_score,
                result.io_score,
                result.score,
                time.time(),
            ),
        )
        conn.commit()
    finally:
        conn.close()
