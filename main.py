
import sys

from PySide6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGridLayout,
    QLabel,
    QPushButton,
    QFrame,
)
from PySide6.QtCore import Qt, QTimer, Slot

from core.bot_manager import BotManager, BOT_CONFIG
from core.scan_callbacks import create_scan_functions


class BotCard(QFrame):
    def __init__(self, bot_name, description, manager):
        super().__init__()

        self.bot_name = bot_name
        self.manager = manager

        self.setObjectName("botCard")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        self.name_label = QLabel(bot_name)
        self.name_label.setObjectName("botName")

        description_label = QLabel(description)
        description_label.setObjectName("description")
        description_label.setWordWrap(True)

        self.status_label = QLabel("● STOPPED")
        self.status_label.setObjectName("stopped")

        self.button = QPushButton("Start bot")
        self.button.setObjectName("botButton")
        self.button.clicked.connect(self.toggle_bot)

        layout.addWidget(self.name_label)
        layout.addWidget(description_label)
        layout.addStretch()
        layout.addWidget(self.status_label)
        layout.addWidget(self.button)

    def toggle_bot(self):
        bot_status = self.manager.get_status()[self.bot_name]
        status = bot_status["status"]

        if status in ("RUNNING", "STARTING"):
            self.manager.stop_bot(self.bot_name)
        elif status not in ("STOPPING", "NOT_IMPLEMENTED"):
            self.manager.start_bot(self.bot_name)

        self.update_status(
            self.manager.get_status()[self.bot_name]
        )

    def update_status(self, bot_status=None):
        if bot_status is None:
            bot_status = self.manager.get_status()[self.bot_name]

        status = bot_status["status"]

        if status == "RUNNING":
            self.status_label.setText("● RUNNING – PAPER MODE")
            self.status_label.setObjectName("running")
            self.button.setText("Stop bot")
            self.button.setEnabled(True)

        elif status == "STARTING":
            self.status_label.setText("● STARTING")
            self.status_label.setObjectName("starting")
            self.button.setText("Stop bot")
            self.button.setEnabled(True)

        elif status == "STOPPING":
            self.status_label.setText("● STOPPING")
            self.status_label.setObjectName("starting")
            self.button.setText("Stopping...")
            self.button.setEnabled(False)

        elif status == "ERROR":
            self.status_label.setText("● ERROR")
            self.status_label.setObjectName("stopped")
            self.button.setText("Retry bot")
            self.button.setEnabled(not bot_status["alive"])

        elif status == "NOT_IMPLEMENTED":
            self.status_label.setText("● NOT IMPLEMENTED")
            self.status_label.setObjectName("notImplemented")
            self.button.setText("Unavailable")
            self.button.setEnabled(False)

        else:
            self.status_label.setText("● STOPPED")
            self.status_label.setObjectName("stopped")
            self.button.setText("Start bot")
            self.button.setEnabled(True)

        details = []
        scan_status = bot_status.get("scan_status")
        if scan_status:
            details.append(f"Scan status: {scan_status}")

        last_attempt = bot_status.get("last_scan_attempt")
        if last_attempt is not None:
            details.append(
                f"Last scan attempt: {last_attempt.isoformat()}"
            )

        last_scan = bot_status.get("last_successful_scan")
        if last_scan is not None:
            details.append(
                f"Last successful scan: {last_scan.isoformat()}"
            )

        last_error = bot_status.get("last_error")
        if last_error:
            details.append(f"Last error: {last_error}")

        result_summary = bot_status.get("last_result_summary")
        if result_summary is not None:
            result_count = result_summary.get("count")
            if result_count is not None:
                details.append(f"Last result count: {result_count}")
            preview = result_summary.get("preview")
            if preview:
                details.append(f"Result preview: {preview}")

        self.status_label.setToolTip("\n".join(details))

        self.status_label.style().unpolish(self.status_label)
        self.status_label.style().polish(self.status_label)


class NexusWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("NEXUS AI - Solana Memecoin Edition")
        self.resize(1150, 780)
        self.setMinimumSize(900, 650)

        # Create the central bot manager.
        self.manager = BotManager(
            auto_restart=True,
            max_restart_attempts=3,
            scan_functions=create_scan_functions(),
        )

        # Start monitoring the bots.
        self.manager.start_watchdog()

        central = QWidget()
        self.setCentralWidget(central)

        main_layout = QVBoxLayout(central)
        main_layout.setContentsMargins(30, 25, 30, 25)
        main_layout.setSpacing(20)

        # Header
        header = QHBoxLayout()

        title = QLabel("NEXUS AI")
        title.setObjectName("mainTitle")

        subtitle = QLabel("SOLANA MEMECOIN EDITION")
        subtitle.setObjectName("subtitle")

        title_layout = QVBoxLayout()
        title_layout.addWidget(title)
        title_layout.addWidget(subtitle)

        mode = QLabel("● PAPER ENGINE NOT IMPLEMENTED")
        mode.setObjectName("paperMode")

        header.addLayout(title_layout)
        header.addStretch()
        header.addWidget(mode)

        main_layout.addLayout(header)

        # Statistics
        stats_layout = QGridLayout()
        stats_layout.setSpacing(15)

        self.stat_values = {}

        stats = [
            ("TOTAL BALANCE", "N/A"),
            ("OPEN POSITIONS", "N/A"),
            ("TOTAL PROFIT / LOSS", "N/A"),
            ("ACTIVE BOTS", "0 / 6"),
        ]

        for index, (name, value) in enumerate(stats):
            card = QFrame()
            card.setObjectName("statCard")

            card_layout = QVBoxLayout(card)

            name_label = QLabel(name)
            name_label.setObjectName("statName")

            value_label = QLabel(value)
            value_label.setObjectName("statValue")

            self.stat_values[name] = value_label

            card_layout.addWidget(name_label)
            card_layout.addWidget(value_label)

            stats_layout.addWidget(card, 0, index)

        main_layout.addLayout(stats_layout)

        # Bots heading
        bots_heading = QLabel("YOUR AI TRADING BOTS")
        bots_heading.setObjectName("sectionTitle")

        main_layout.addWidget(bots_heading)

        # Six independent bot cards
        bots_layout = QGridLayout()
        bots_layout.setSpacing(15)

        self.bot_cards = {}

        for index, (name, description) in enumerate(BOT_CONFIG.items()):
            bot_card = BotCard(name, description, self.manager)

            self.bot_cards[name] = bot_card
            bots_layout.addWidget(bot_card, index // 3, index % 3)

        main_layout.addLayout(bots_layout)
        self.manager.status_changed.connect(
            self._on_bot_status_changed
        )

        # Footer
        footer = QLabel(
            "NEXUS AI | Solana ecosystem | "
            "Simulation only – no real trades are executed."
        )
        footer.setObjectName("footer")
        footer.setAlignment(Qt.AlignmentFlag.AlignCenter)

        main_layout.addStretch()
        main_layout.addWidget(footer)

        # Refresh dashboard status every second.
        self.refresh_timer = QTimer(self)
        self.refresh_timer.timeout.connect(self.refresh_dashboard)
        self.refresh_timer.start(1000)
        self._shutdown_requested = False
        self._shutdown_complete = False
        self._shutdown_timer = QTimer(self)
        self._shutdown_timer.setInterval(50)
        self._shutdown_timer.timeout.connect(
            self._finish_shutdown_if_stopped
        )

        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #0b1020;
                color: #edf2ff;
                font-family: Segoe UI;
            }

            QLabel#mainTitle {
                font-size: 32px;
                font-weight: 800;
                color: #ffffff;
            }

            QLabel#subtitle {
                font-size: 11px;
                font-weight: bold;
                color: #9b83ff;
                letter-spacing: 2px;
            }

            QLabel#paperMode {
                color: #66e6b1;
                background-color: #12352f;
                padding: 10px 16px;
                border-radius: 8px;
                font-weight: bold;
            }

            QFrame#statCard, QFrame#botCard {
                background-color: #151d32;
                border: 1px solid #283450;
                border-radius: 12px;
            }

            QLabel#statName {
                color: #91a0bd;
                font-size: 10px;
                font-weight: bold;
            }

            QLabel#statValue {
                color: #ffffff;
                font-size: 23px;
                font-weight: bold;
            }

            QLabel#sectionTitle {
                color: #ffffff;
                font-size: 17px;
                font-weight: bold;
                padding-top: 8px;
            }

            QLabel#botName {
                color: #bbaaff;
                font-size: 14px;
                font-weight: bold;
            }

            QLabel#description {
                color: #aab5cc;
                font-size: 12px;
            }

            QLabel#stopped {
                color: #ff8585;
                font-size: 11px;
                font-weight: bold;
            }

            QLabel#running {
                color: #66e6b1;
                font-size: 11px;
                font-weight: bold;
            }

            QLabel#starting {
                color: #ffd166;
                font-size: 11px;
                font-weight: bold;
            }

            QLabel#notImplemented {
                color: #91a0bd;
                font-size: 11px;
                font-weight: bold;
            }

            QPushButton#botButton {
                background-color: #7049e8;
                color: white;
                border: none;
                border-radius: 7px;
                padding: 10px;
                font-weight: bold;
            }

            QPushButton#botButton:hover {
                background-color: #8968f5;
            }

            QLabel#footer {
                color: #687793;
                font-size: 10px;
            }
        """)

        self.refresh_dashboard()

    def refresh_dashboard(self):
        active_bots = 0
        statuses = self.manager.get_status()

        for bot_name, bot_card in self.bot_cards.items():
            status = statuses[bot_name]["status"]
            bot_card.update_status(statuses[bot_name])

            if status in ("RUNNING", "STARTING"):
                active_bots += 1

        self.stat_values["ACTIVE BOTS"].setText(
            f"{active_bots} / 6"
        )

    @Slot(str, object)
    def _on_bot_status_changed(self, bot_name, status):
        bot_card = self.bot_cards.get(bot_name)
        if bot_card is not None:
            bot_card.update_status(status)

        self.refresh_dashboard()

    def _finish_shutdown_if_stopped(self):
        if not self.manager.is_shutdown_complete():
            return

        self._shutdown_timer.stop()
        self._shutdown_complete = True
        self.close()

    def closeEvent(self, event):
        if self._shutdown_complete:
            self.refresh_timer.stop()
            event.accept()
            return

        event.ignore()

        if self._shutdown_requested:
            return

        self._shutdown_requested = True
        self.refresh_timer.stop()
        self.manager.shutdown()
        self._shutdown_timer.start()
        self._finish_shutdown_if_stopped()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    window = NexusWindow()
    window.show()

    sys.exit(app.exec())
