import threading
import time
from datetime import timezone

import pytest
from PySide6.QtCore import QCoreApplication, QObject, QThread, Slot

from core.bot_manager import BOT_CONFIG, BotManager
from core.provider_errors import ProviderError


@pytest.fixture(scope="session")
def qapp():
    return QCoreApplication.instance() or QCoreApplication([])


def wait_until(predicate, app, timeout=2.0):
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.005)

    app.processEvents()
    return predicate()


def make_manager(scan_functions, scan_interval=30.0):
    return BotManager(
        auto_restart=False,
        scan_interval=scan_interval,
        scan_functions=scan_functions,
    )


def stop_and_wait(manager, app):
    manager.shutdown()
    assert wait_until(manager.is_shutdown_complete, app)


def test_bot_starts_scans_and_stops_successfully(qapp):
    scanned = threading.Event()

    def scan():
        scanned.set()
        return ["token"]

    manager = make_manager(
        {"NEW GEM HUNTER": scan},
        scan_interval=30,
    )

    assert manager.start_bot("NEW GEM HUNTER") is True
    assert wait_until(
        lambda: manager.get_status()["NEW GEM HUNTER"]["status"]
        == "RUNNING",
        qapp,
    )
    assert scanned.is_set()

    last_scan = manager.get_status()["NEW GEM HUNTER"][
        "last_successful_scan"
    ]
    assert last_scan is not None
    assert last_scan.tzinfo == timezone.utc
    status = manager.get_status()["NEW GEM HUNTER"]
    assert status["scan_status"] == "SUCCESS"
    assert status["last_scan_attempt"] is not None
    assert status["last_scan_attempt"].tzinfo == timezone.utc
    assert status["last_result_summary"]["count"] == 1
    assert "token" in status["last_result_summary"]["preview"]

    assert manager.stop_bot("NEW GEM HUNTER") is True
    assert wait_until(
        lambda: manager.get_status()["NEW GEM HUNTER"]["status"]
        == "STOPPED",
        qapp,
    )


def test_starting_running_bot_does_not_create_duplicate(qapp):
    scan_entered = threading.Event()
    release_scan = threading.Event()
    scan_count = 0
    count_lock = threading.Lock()

    def scan():
        nonlocal scan_count
        with count_lock:
            scan_count += 1
        scan_entered.set()
        release_scan.wait(timeout=2)

    manager = make_manager(
        {"NEW GEM HUNTER": scan},
        scan_interval=30,
    )

    try:
        assert manager.start_bot("NEW GEM HUNTER") is True
        assert scan_entered.wait(timeout=1)
        assert manager.start_bot("NEW GEM HUNTER") is False
        assert scan_count == 1
    finally:
        release_scan.set()
        stop_and_wait(manager, qapp)


def test_stopping_stopped_or_unimplemented_bot_is_safe(qapp):
    manager = make_manager({})

    assert manager.get_status()["NEW GEM HUNTER"]["status"] == (
        "NOT_IMPLEMENTED"
    )
    assert manager.start_bot("NEW GEM HUNTER") is False
    assert manager.stop_bot("NEW GEM HUNTER") is False

    implemented_manager = make_manager(
        {"NEW GEM HUNTER": lambda: None}
    )
    assert implemented_manager.stop_bot("NEW GEM HUNTER") is False
    assert implemented_manager.get_status()["NEW GEM HUNTER"][
        "status"
    ] == "STOPPED"


def test_worker_exception_is_reported(qapp):
    def failing_scan():
        raise RuntimeError("scan failed")

    manager = make_manager(
        {"NEW GEM HUNTER": failing_scan}
    )

    assert manager.start_bot("NEW GEM HUNTER") is True
    assert wait_until(
        lambda: manager.get_status()["NEW GEM HUNTER"]["status"]
        == "ERROR",
        qapp,
    )

    status = manager.get_status()["NEW GEM HUNTER"]
    assert status["scan_status"] == "FAILED"
    assert status["last_scan_attempt"] is not None
    assert status["last_error"] == "scan failed"
    assert status["last_successful_scan"] is None


def test_empty_scan_is_distinguished_from_failure(qapp):
    manager = make_manager(
        {"NEW GEM HUNTER": lambda: []},
        scan_interval=30,
    )

    try:
        assert manager.start_bot("NEW GEM HUNTER") is True
        assert wait_until(
            lambda: manager.get_status()["NEW GEM HUNTER"][
                "scan_status"
            ] == "EMPTY",
            qapp,
        )

        status = manager.get_status()["NEW GEM HUNTER"]
        assert status["status"] == "RUNNING"
        assert status["last_scan_attempt"] is not None
        assert status["last_successful_scan"] is not None
        assert status["last_error"] is None
    finally:
        stop_and_wait(manager, qapp)


def test_invalid_result_size_is_reported_as_scan_failure(qapp):
    class InvalidResult:
        def __len__(self):
            raise RuntimeError("invalid result size")

    manager = make_manager(
        {"NEW GEM HUNTER": InvalidResult},
    )

    assert manager.start_bot("NEW GEM HUNTER") is True
    assert wait_until(
        lambda: manager.get_status()["NEW GEM HUNTER"]["status"]
        == "ERROR",
        qapp,
    )

    status = manager.get_status()["NEW GEM HUNTER"]
    assert status["scan_status"] == "FAILED"
    assert status["last_error"] == "invalid result size"
    assert status["last_successful_scan"] is None


def test_watchdog_restarts_failed_worker(qapp):
    scan_calls = 0
    recovered = threading.Event()

    def scan():
        nonlocal scan_calls
        scan_calls += 1
        if scan_calls == 1:
            raise RuntimeError("temporary failure")
        recovered.set()

    manager = BotManager(
        auto_restart=True,
        max_restart_attempts=1,
        scan_interval=30,
        scan_functions={"NEW GEM HUNTER": scan},
    )
    manager.start_watchdog()

    try:
        assert manager.start_bot("NEW GEM HUNTER") is True
        assert wait_until(
            lambda: (
                recovered.is_set()
                and manager.get_status()["NEW GEM HUNTER"]["status"]
                == "RUNNING"
            ),
            qapp,
            timeout=5,
        )
        assert scan_calls == 2
        assert manager.get_status()["NEW GEM HUNTER"][
            "scan_status"
        ] == "EMPTY"
        assert manager.get_status()["NEW GEM HUNTER"]["last_error"] is None
    finally:
        stop_and_wait(manager, qapp)


def test_watchdog_does_not_restart_a_manually_stopped_worker(qapp):
    scan_entered = threading.Event()
    release_scan = threading.Event()
    scan_calls = 0

    def failing_scan():
        nonlocal scan_calls
        scan_calls += 1
        scan_entered.set()
        release_scan.wait(timeout=2)
        raise RuntimeError("scan interrupted")

    manager = BotManager(
        auto_restart=True,
        max_restart_attempts=1,
        scan_interval=30,
        scan_functions={"NEW GEM HUNTER": failing_scan},
    )
    manager.start_watchdog()

    try:
        assert manager.start_bot("NEW GEM HUNTER") is True
        assert scan_entered.wait(timeout=1)
        assert manager.stop_bot("NEW GEM HUNTER") is True
        release_scan.set()

        assert wait_until(
            lambda: (
                manager.get_status()["NEW GEM HUNTER"]["status"]
                == "STOPPED"
                and manager.get_status()["NEW GEM HUNTER"]["scan_status"]
                == "FAILED"
            ),
            qapp,
        )
        deadline = time.monotonic() + 2.2
        while time.monotonic() < deadline:
            qapp.processEvents()
            time.sleep(0.01)

        assert scan_calls == 1
        assert manager.restart_attempts["NEW GEM HUNTER"] == 0
    finally:
        stop_and_wait(manager, qapp)


def test_missing_scan_function_never_reports_running():
    manager = make_manager({})

    assert manager.start_bot("NEW GEM HUNTER") is False
    status = manager.get_status()["NEW GEM HUNTER"]
    assert status["status"] == "NOT_IMPLEMENTED"
    assert status["scan_status"] == "NOT_IMPLEMENTED"
    assert status["alive"] is False
    assert status["last_scan_attempt"] is None
    assert status["last_successful_scan"] is None


def test_status_signal_is_delivered_on_receiver_thread(qapp):
    class StatusReceiver(QObject):
        def __init__(self):
            super().__init__()
            self.received = []

        @Slot(str, object)
        def receive_status(self, name, status):
            self.received.append(
                (name, status["status"], QThread.currentThread() == self.thread())
            )

    receiver = StatusReceiver()
    manager = make_manager(
        {"NEW GEM HUNTER": lambda: None},
        scan_interval=30,
    )
    manager.status_changed.connect(receiver.receive_status)

    try:
        assert manager.start_bot("NEW GEM HUNTER") is True
        assert wait_until(
            lambda: any(
                name == "NEW GEM HUNTER" and status == "RUNNING"
                for name, status, _ in receiver.received
            ),
            qapp,
        )
        assert all(on_receiver_thread for _, _, on_receiver_thread in receiver.received)
    finally:
        stop_and_wait(manager, qapp)


def test_stop_all_stops_every_active_worker(qapp):
    scanned = {
        "NEW GEM HUNTER": threading.Event(),
        "MOMENTUM BOT": threading.Event(),
    }
    manager = make_manager(
        {
            name: event.set
            for name, event in scanned.items()
        },
        scan_interval=30,
    )

    try:
        manager.start_all()
        assert wait_until(
            lambda: all(event.is_set() for event in scanned.values()),
            qapp,
        )
        assert wait_until(
            lambda: all(
                manager.get_status()[name]["status"] == "RUNNING"
                for name in scanned
            ),
            qapp,
        )

        manager.stop_all()
        assert wait_until(
            lambda: all(
                manager.get_status()[name]["status"] == "STOPPED"
                and not manager.get_status()[name]["alive"]
                for name in scanned
            ),
            qapp,
        )
    finally:
        stop_and_wait(manager, qapp)


def test_start_all_does_not_duplicate_workers(qapp):
    scanned = {
        "NEW GEM HUNTER": threading.Event(),
        "MOMENTUM BOT": threading.Event(),
    }
    manager = make_manager(
        {
            name: event.set
            for name, event in scanned.items()
        },
        scan_interval=30,
    )

    try:
        first_result = manager.start_all()
        assert wait_until(
            lambda: all(event.is_set() for event in scanned.values()),
            qapp,
        )
        second_result = manager.start_all()

        assert all(first_result[name] for name in scanned)
        assert all(not second_result[name] for name in scanned)
        for name in BOT_CONFIG:
            if name not in scanned:
                assert manager.get_status()[name]["status"] == (
                    "NOT_IMPLEMENTED"
                )
    finally:
        stop_and_wait(manager, qapp)


def test_start_all_after_stop_all_keeps_watchdog_active(qapp):
    scan_count = 0
    second_scan = threading.Event()

    def scan():
        nonlocal scan_count
        scan_count += 1
        if scan_count >= 2:
            second_scan.set()
        return ["token"]

    manager = make_manager(
        {"NEW GEM HUNTER": scan},
        scan_interval=30,
    )

    try:
        assert manager.start_all()["NEW GEM HUNTER"] is True
        assert wait_until(
            lambda: manager.get_status()["NEW GEM HUNTER"]["status"]
            == "RUNNING",
            qapp,
        )

        manager.stop_all()
        assert wait_until(
            lambda: (
                manager.get_status()["NEW GEM HUNTER"]["status"]
                == "STOPPED"
                and not manager.get_status()["NEW GEM HUNTER"]["alive"]
            ),
            qapp,
        )
        assert not manager.is_shutdown_complete()

        assert manager.start_all()["NEW GEM HUNTER"] is True
        assert wait_until(
            lambda: second_scan.is_set()
            and manager.get_status()["NEW GEM HUNTER"]["status"]
            == "RUNNING",
            qapp,
        )
    finally:
        stop_and_wait(manager, qapp)


def test_shutdown_prevents_worker_and_watchdog_restart(qapp):
    scan_entered = threading.Event()
    release_scan = threading.Event()
    scan_calls = 0

    def scan():
        nonlocal scan_calls
        scan_calls += 1
        scan_entered.set()
        release_scan.wait(timeout=2)
        return ["token"]

    manager = BotManager(
        auto_restart=True,
        max_restart_attempts=1,
        scan_functions={"NEW GEM HUNTER": scan},
    )
    manager.start_watchdog()

    try:
        assert manager.start_bot("NEW GEM HUNTER") is True
        assert scan_entered.wait(timeout=1)

        manager.shutdown()
        assert manager.start_bot("NEW GEM HUNTER") is False
        assert manager.start_watchdog() is False
        assert all(not started for started in manager.start_all().values())

        release_scan.set()
        assert wait_until(manager.is_shutdown_complete, qapp)
        assert scan_calls == 1
    finally:
        release_scan.set()
        stop_and_wait(manager, qapp)


def test_provider_failure_marks_scan_failed_and_retries_next_interval(qapp):
    calls = 0

    def scan():
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ProviderError("HTTP 429 rate limit")
        return ["token"]

    manager = make_manager(
        {"NEW GEM HUNTER": scan},
        scan_interval=0.2,
    )

    try:
        assert manager.start_bot("NEW GEM HUNTER") is True
        assert wait_until(
            lambda: (
                manager.get_status()["NEW GEM HUNTER"]["scan_status"]
                == "FAILED"
                and manager.get_status()["NEW GEM HUNTER"]["status"]
                == "RUNNING"
            ),
            qapp,
        )
        failed_status = manager.get_status()["NEW GEM HUNTER"]
        assert failed_status["last_error"] == "HTTP 429 rate limit"

        assert wait_until(
            lambda: (
                manager.get_status()["NEW GEM HUNTER"]["scan_status"]
                == "SUCCESS"
                and manager.get_status()["NEW GEM HUNTER"][
                    "last_error"
                ] is None
            ),
            qapp,
        )
        assert calls == 2
    finally:
        stop_and_wait(manager, qapp)
