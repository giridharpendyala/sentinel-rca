"""Shared fault-injection primitives used by the synthetic microservices.

Each service owns exactly one process-wide FaultState instance. incident-controller
is the only caller of a service's /admin/fault endpoint, which arms/disarms this
state. Request-handling code checks the active fault inline (apply_latency,
maybe_raise) and two background workers handle the resource-pressure faults
(cpu_load, memory_leak) which can't be expressed as a single inline check.
"""

from __future__ import annotations

import random
import threading
import time
from typing import Any, Optional


class FaultState:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._active: Optional[dict[str, Any]] = None
        self._memory_ballast: list[bytes] = []
        self._cpu_stop = threading.Event()
        self._cpu_threads: list[threading.Thread] = []
        self._mem_stop = threading.Event()
        self._mem_thread: Optional[threading.Thread] = None

    def arm(self, fault_type: str, params: dict[str, Any] | None = None) -> None:
        params = params or {}
        with self._lock:
            self._active = {"type": fault_type, "params": params}

        if fault_type == "cpu_load":
            self._start_cpu_load(cores=int(params.get("cores", 1)))
        elif fault_type == "memory_leak":
            self._start_memory_leak(mb_per_tick=float(params.get("mb_per_tick", 5)))

    def disarm(self) -> None:
        with self._lock:
            self._active = None
        self._stop_cpu_load()
        self._stop_memory_leak()

    def get(self) -> Optional[dict[str, Any]]:
        with self._lock:
            return dict(self._active) if self._active else None

    def is_active(self, fault_type: str) -> bool:
        active = self.get()
        return bool(active and active["type"] == fault_type)

    # --- inline checks used by request handlers ---

    def apply_latency(self) -> None:
        """Sleep for the configured extra delay if a latency fault is armed."""
        active = self.get()
        if active and active["type"] == "latency":
            time.sleep(float(active["params"].get("delay_seconds", 1.0)))

    def maybe_raise(self, exc: type[Exception] = RuntimeError, message: str = "injected failure") -> None:
        """Probabilistically raise if an error_rate/exception fault is armed."""
        active = self.get()
        if active and active["type"] in ("error_rate", "exception"):
            probability = float(active["params"].get("probability", 0.5))
            if random.random() < probability:
                raise exc(message)

    # --- background resource-pressure workers ---

    def _start_cpu_load(self, cores: int) -> None:
        self._stop_cpu_load()
        self._cpu_stop.clear()

        def burn() -> None:
            while not self._cpu_stop.is_set():
                for _ in range(200_000):
                    pass
                time.sleep(0)  # yield without meaningfully throttling the loop

        self._cpu_threads = [threading.Thread(target=burn, daemon=True) for _ in range(cores)]
        for t in self._cpu_threads:
            t.start()

    def _stop_cpu_load(self) -> None:
        self._cpu_stop.set()
        self._cpu_threads = []

    def _start_memory_leak(self, mb_per_tick: float) -> None:
        self._stop_memory_leak()
        self._mem_stop.clear()

        def grow() -> None:
            while not self._mem_stop.is_set():
                self._memory_ballast.append(bytearray(int(mb_per_tick * 1024 * 1024)))
                time.sleep(1.0)

        self._mem_thread = threading.Thread(target=grow, daemon=True)
        self._mem_thread.start()

    def _stop_memory_leak(self) -> None:
        self._mem_stop.set()
        self._mem_thread = None
        self._memory_ballast.clear()
