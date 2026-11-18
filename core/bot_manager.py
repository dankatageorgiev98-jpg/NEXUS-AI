import threading
from collections.abc import Sized
from datetime import datetime, timezone
from typing import Callable

from PySide6.QtCore import QObject, Signal, Slot

from core.activity_logger import ActivityLogger
from core.provider_errors import ProviderError


BOT_CONFIG = {
    "NEW GEM HUNTER": "Scans for newly launched Solana meme coins.",
    "WHALE TRACKER": "Monitors large wallet transactions.",
    "MOMENTUM BOT": "Analyses price momentum.",
    "VOLUME SCANNER": "Analyses trading volume and liquidity.",
    "SAFETY BOT": "Checks token and transaction risks.",
    "AI MASTER": "Combines the analysis of the other bots.",
}

ScanFunction = Callable[[], object]
SCAN_STATUS_NOT_RUN = "NOT_RUN"
SCAN_STATUS_RUNNING = "RUNNING"
SCAN_STATUS_SUCCESS = "SUCCESS"
SCAN_STATUS_EMPTY = "EMPTY"
SCAN_STATUS_FAILED = "FAILED"
SCAN_STATUS_NOT_IMPLEMENTED = "NOT_IMPLEMENTED"


class BotWorker(QObject):
    """Runs one bot's scan function on a dedicated worker thread."""

    status_changed = Signal(str, object)

    def __init__(
        self,
        name,
        description,
        scan_function=None,
        scan_interval=30.0,
    ):
        super().__init__()

        if scan_interval <= 0:
            raise ValueError("scan_interval must be greater than zero")

        self.name = name
        self.description = description
        self.scan_function: ScanFunction | None = scan_function
        self.scan_interval = scan_interval

        self._status = (
            "STOPPED" if scan_function is not None else "NOT_IMPLEMENTED"
        )
        self._scan_status = (
            SCAN_STATUS_NOT_RUN
            if scan_function is not None
            else SCAN_STATUS_NOT_IMPLEMENTED
        )
        self._last_scan_attempt = None
        self._last_successful_scan = None
        self._last_error = None
        self._last_result_summary = None

        self._stop_event = threading.Event()
        self._thread = None
        self._lock = threading.RLock()

    def start(self):
        with self._lock:
            if self.scan_function is None:
                self._set_status_locked("NOT_IMPLEMENTED")
                return False

            if (
                self._thread is not None
                and self._thread.is_alive()
            ):
                return False

            self._stop_event = threading.Event()
            self._set_status_locked("STARTING")

            self._thread = threading.Thread(
                target=self._run,
                name=self.name.replace(" ", "_"),
                daemon=True,
            )

            try:
                self._thread.start()
            except RuntimeError as error:
                self._thread = None
                self._set_status_locked("ERROR", str(error))
                ActivityLogger.error(
                    f"{self.name} could not start: {error}"
                )
                return False

        return True

    def _run(self):
        while not self._stop_event.is_set():
            self._set_scan_state(
                SCAN_STATUS_RUNNING,
                attempted=True,
            )

            try:
                result = self.scan_function()
                scan_status = (
                    SCAN_STATUS_EMPTY
                    if result is None
                    or isinstance(result, Sized) and len(result) == 0
                    else SCAN_STATUS_SUCCESS
                )
                result_summary = self._summarize_result(result)
            except Exception as error:
                if isinstance(error, ProviderError):
                    lifecycle_status = (
                        "STOPPING"
                        if self._stop_event.is_set()
                        else "RUNNING"
                    )
                    self._set_scan_state(
                        SCAN_STATUS_FAILED,
                        error=str(error),
                        lifecycle_status=lifecycle_status,
                    )
                    ActivityLogger.warning(
                        f"{self.name} scan failed due to provider error: "
                        f"{error}"
                    )
                    if self._stop_event.is_set():
                        return
                    if self._stop_event.wait(self.scan_interval):
                        break
                    continue

                lifecycle_status = (
                    "STOPPING"
                    if self._stop_event.is_set()
                    else "ERROR"
                )
                self._set_scan_state(
                    SCAN_STATUS_FAILED,
                    error=str(error),
                    lifecycle_status=lifecycle_status,
                )

                if lifecycle_status == "ERROR":
                    ActivityLogger.error(
                        f"{self.name} scan failed: {error}"
                    )
                else:
                    ActivityLogger.warning(
                        f"{self.name} stopped while its scan failed: {error}"
                    )
                return

            lifecycle_status = (
                "STOPPING"
                if self._stop_event.is_set()
                else "RUNNING"
            )
            self._set_scan_state(
                scan_status,
                successful=True,
                result_summary=result_summary,
                lifecycle_status=lifecycle_status,
            )

            if self._stop_event.is_set():
                break

            if self._stop_event.wait(self.scan_interval):
                break

        self._set_status("STOPPING")
        ActivityLogger.info(f"{self.name} stopped.")

    def stop(self):
        with self._lock:
            thread = self._thread

            if thread is None or not thread.is_alive():
                if self._status not in ("ERROR", "NOT_IMPLEMENTED"):
                    self._set_status_locked("STOPPED")
                return False

            self._stop_event.set()
            self._set_status_locked("STOPPING")
            return True

    def is_alive(self):
        with self._lock:
            return self._thread is not None and self._thread.is_alive()

    def get_status(self):
        with self._lock:
            if (
                self._status == "STOPPING"
                and (
                    self._thread is None
                    or not self._thread.is_alive()
                )
            ):
                self._set_status_locked("STOPPED")

            return {
                "status": self._status,
                "alive": self._thread is not None and self._thread.is_alive(),
                "scan_status": self._scan_status,
                "last_scan_attempt": self._last_scan_attempt,
                "last_successful_scan": self._last_successful_scan,
                "last_error": self._last_error,
                "last_result_summary": self._last_result_summary,
            }

    def _set_status(self, status, error=None):
        with self._lock:
            self._set_status_locked(status, error)

    def _set_scan_state(
        self,
        scan_status,
        attempted=False,
        successful=False,
        error=None,
        result_summary=None,
        lifecycle_status=None,
    ):
        with self._lock:
            self._scan_status = scan_status

            if attempted:
                self._last_scan_attempt = datetime.now(timezone.utc)

            if successful:
                self._last_successful_scan = datetime.now(timezone.utc)
                self._last_error = None
                self._last_result_summary = result_summary

            if error is not None:
                self._last_error = error

            if lifecycle_status is not None:
                self._status = lifecycle_status

            snapshot = self._snapshot_locked()

        self.status_changed.emit(self.name, snapshot)

    def _set_status_locked(self, status, error=None):
        self._status = status
        if error is not None:
            self._last_error = error

        self.status_changed.emit(self.name, self._snapshot_locked())

    def _snapshot_locked(self):
        return {
            "status": self._status,
            "alive": self._thread is not None and self._thread.is_alive(),
            "scan_status": self._scan_status,
            "last_scan_attempt": self._last_scan_attempt,
            "last_successful_scan": self._last_successful_scan,
            "last_error": self._last_error,
            "last_result_summary": self._last_result_summary,
        }

    @staticmethod
    def _summarize_result(result):
        if result is None:
            return {"count": 0, "preview": "None"}

        count = len(result) if isinstance(result, Sized) else None
        if isinstance(result, (list, tuple)):
            preview_value = result[:2]
        else:
            preview_value = result

        return {
            "count": count,
            "preview": repr(preview_value)[:1000],
        }


class BotManager(QObject):
    """Controls bot workers and monitors their health."""

    status_changed = Signal(str, object)

    def __init__(
        self,
        auto_restart=True,
        max_restart_attempts=3,
        scan_interval=30.0,
        scan_functions=None,
    ):
        super().__init__()

        if max_restart_attempts < 0:
            raise ValueError("max_restart_attempts cannot be negative")

        scan_functions = scan_functions or {}
        unknown_bots = set(scan_functions) - set(BOT_CONFIG)
        if unknown_bots:
            raise ValueError(
                f"Unknown bots in scan_functions: {sorted(unknown_bots)}"
            )

        self.auto_restart = auto_restart
        self.max_restart_attempts = max_restart_attempts
        self.scan_interval = scan_interval
        self.restart_attempts = {name: 0 for name in BOT_CONFIG}

        self.bots = {
            name: BotWorker(
                name,
                description,
                scan_function=scan_functions.get(name),
                scan_interval=scan_interval,
            )
            for name, description in BOT_CONFIG.items()
        }

        for bot in self.bots.values():
            bot.status_changed.connect(self._handle_worker_status)

        self._watchdog_stop = threading.Event()
        self._watchdog_thread = None
        self._state_lock = threading.RLock()
        self._shutting_down = False

    def start_bot(self, name):
        with self._state_lock:
            if self._shutting_down:
                return False
            bot = self._get_bot(name)
            started = bot.start()

        if started:
            ActivityLogger.info(f"Manager activated {name}.")
        elif bot.get_status()["status"] == "NOT_IMPLEMENTED":
            ActivityLogger.warning(
                f"{name} cannot start: no scan function is configured."
            )

        return started

    def stop_bot(self, name):
        bot = self._get_bot(name)
        stopped = bot.stop()

        if stopped:
            ActivityLogger.info(f"Manager requested stop for {name}.")

        return stopped

    def start_all(self):
        with self._state_lock:
            if self._shutting_down:
                return {name: False for name in self.bots}
            results = {
                name: self.start_bot(name)
                for name in self.bots
            }
            self.start_watchdog()
            return results

    def stop_all(self):
        with self._state_lock:
            for bot in self.bots.values():
                bot.stop()

        ActivityLogger.info("Stop requested for all bots.")

    def shutdown(self):
        with self._state_lock:
            self._shutting_down = True
            self._watchdog_stop.set()
            self.stop_all()

    def get_status(self):
        return {
            name: bot.get_status()
            for name, bot in self.bots.items()
        }

    def is_shutdown_complete(self):
        bots_stopped = all(
            not bot.is_alive()
            for bot in self.bots.values()
        )
        watchdog_stopped = (
            self._watchdog_thread is None
            or not self._watchdog_thread.is_alive()
        )
        return bots_stopped and watchdog_stopped

    def start_watchdog(self):
        with self._state_lock:
            if self._shutting_down:
                return False
            if (
                self._watchdog_thread is not None
                and self._watchdog_thread.is_alive()
            ):
                return False

            self._watchdog_stop.clear()
            self._watchdog_thread = threading.Thread(
                target=self._watchdog_loop,
                name="NEXUS_WATCHDOG",
                daemon=True,
            )
            self._watchdog_thread.start()

        ActivityLogger.info("Watchdog started.")
        return True

    def _get_bot(self, name):
        bot = self.bots.get(name)
        if bot is None:
            raise ValueError(f"Unknown bot: {name}")
        return bot

    @Slot(str, object)
    def _handle_worker_status(self, name, status):
        if status["status"] == "RUNNING":
            self.restart_attempts[name] = 0

        self.status_changed.emit(name, status)

    def _watchdog_loop(self):
        while not self._watchdog_stop.wait(2):
            if not self.auto_restart:
                continue

            for name, bot in self.bots.items():
                with self._state_lock:
                    if self._shutting_down:
                        return
                    status = bot.get_status()

                    if status["status"] != "ERROR" or status["alive"]:
                        continue

                    if (
                        self.restart_attempts[name]
                        >= self.max_restart_attempts
                    ):
                        continue

                    self.restart_attempts[name] += 1
                    ActivityLogger.warning(
                        f"Watchdog restarting {name}. "
                        f"Attempt {self.restart_attempts[name]}."
                    )
                    bot.start()
