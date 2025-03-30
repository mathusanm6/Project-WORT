"""
Battery management module for Rasptank.
This module handles battery state tracking, persistence, and status reporting.
"""

import json
import os
import threading
import time
from enum import Enum
from typing import Optional


class PowerSource(Enum):
    """Enum for tracking power source type."""

    BATTERY = "battery"
    WIRED = "wired"


class BatteryManager:
    """
    Manages battery status for Rasptank.
    - Tracks battery percentage
    - Persists between program runs
    - Simulates battery discharge when running on battery
    - Provides battery status for MQTT reporting
    """

    BATTERY_STATE_FILE = "/tmp/rasptank_battery_state.json"
    DEFAULT_DISCHARGE_RATE = 0.5  # % per hour
    DEFAULT_BATTERY_PERCENTAGE = 100.0
    SAVE_THROTTLE_SECONDS = 60

    def __init__(self, logger):
        self.logger = logger
        self.power_source = PowerSource.WIRED
        self.battery_percentage = self.DEFAULT_BATTERY_PERCENTAGE
        self.discharge_rate = self.DEFAULT_DISCHARGE_RATE
        self.last_update_time = time.time()
        self.last_save_time = 0
        self._running = False
        self._thread = None
        self._lock = threading.Lock()

        self._load_state()
        self.last_update_time = time.time()  # Ensure it's set correctly after loading

    def start(self):
        if self._thread is not None and self._thread.is_alive():
            return

        self._running = True
        self._thread = threading.Thread(target=self._battery_monitor_thread, daemon=True)
        self._thread.start()
        self.logger.infow(
            "Battery management system started",
            "power_source",
            self.power_source.value,
            "battery_percentage",
            f"{self.battery_percentage:.1f}%",
        )

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=1.0)
        self._save_state()
        self.logger.infow(
            "Battery management system stopped",
            "battery_percentage",
            f"{self.battery_percentage:.1f}%",
        )

    def set_power_source(self, source: PowerSource):
        with self._lock:
            # No need to apply discharge here as the battery monitor thread
            # is consistently updating the battery percentage
            self.power_source = source
            self.last_update_time = time.time()
            self._save_state()
            self.logger.infow(
                "Power source changed",
                "power_source",
                source.value,
                "battery_percentage",
                f"{self.battery_percentage:.1f}%",
            )

    def reset_battery(self):
        with self._lock:
            self.battery_percentage = self.DEFAULT_BATTERY_PERCENTAGE
            self.last_update_time = time.time()
            self._save_state()
            self.logger.infow(
                "Battery reset to full charge",
                "battery_percentage",
                f"{self.battery_percentage:.1f}%",
            )

    def get_battery_percentage(self) -> float:
        with self._lock:
            if self.power_source == PowerSource.WIRED:
                return 100.0
            # No need to apply discharge here as the battery monitor thread
            # is consistently updating the battery percentage
            return self.battery_percentage

    def _battery_monitor_thread(self):
        while self._running:
            if self.power_source == PowerSource.BATTERY:
                with self._lock:
                    # Calculate time since last update
                    current_time = time.time()
                    elapsed_hours = (current_time - self.last_update_time) / 3600.0

                    # Update battery percentage
                    discharge_amount = elapsed_hours * self.discharge_rate
                    self.battery_percentage = max(0.0, self.battery_percentage - discharge_amount)
                    self.last_update_time = current_time

                    # Periodically save state to disk
                    if current_time - self.last_save_time > self.SAVE_THROTTLE_SECONDS:
                        self._save_state()

                    # Log battery discharge
                    self.logger.debugw(
                        "Battery discharged",
                        "elapsed_hours",
                        elapsed_hours,
                        "discharge_amount",
                        discharge_amount,
                        "battery_percentage",
                        self.battery_percentage,
                    )

                    # Log if battery is getting low
                    if self.battery_percentage < 20.0:
                        self.logger.warnw(
                            "Battery is running low",
                            "battery_percentage",
                            f"{self.battery_percentage:.1f}%",
                        )

            # Check every 1 second
            time.sleep(1.0)

    def _save_state(self):
        try:
            state = {
                "power_source": self.power_source.value,
                "battery_percentage": self.battery_percentage,
                "last_update_time": self.last_update_time,
                "discharge_rate": self.discharge_rate,
            }
            with open(self.BATTERY_STATE_FILE, "w") as f:
                json.dump(state, f)
            self.last_save_time = time.time()
            self.logger.debugw("Battery state saved to disk", "file", self.BATTERY_STATE_FILE)
        except Exception as e:
            self.logger.errorw(
                "Failed to save battery state", "error", str(e), "file", self.BATTERY_STATE_FILE
            )

    def _load_state(self):
        if not os.path.exists(self.BATTERY_STATE_FILE):
            self.logger.infow("No saved battery state found, using defaults")
            return
        try:
            with open(self.BATTERY_STATE_FILE, "r") as f:
                state = json.load(f)
            self.power_source = PowerSource(state.get("power_source", PowerSource.WIRED.value))
            self.battery_percentage = float(
                state.get("battery_percentage", self.DEFAULT_BATTERY_PERCENTAGE)
            )
            self.last_update_time = float(state.get("last_update_time", time.time()))
            self.discharge_rate = float(state.get("discharge_rate", self.DEFAULT_DISCHARGE_RATE))
            self.logger.infow(
                "Loaded saved battery state",
                "power_source",
                self.power_source.value,
                "battery_percentage",
                f"{self.battery_percentage:.1f}%",
            )
        except Exception as e:
            self.logger.errorw(
                "Failed to load battery state",
                "error",
                str(e),
                "file",
                self.BATTERY_STATE_FILE,
                "using_defaults",
                True,
            )


def setup_power_source_prompt(logger):
    print("\n===== Rasptank Power Source Configuration =====")
    print("Is the Rasptank running on batteries or connected to power?")
    print("1. Running on batteries")
    print("2. Connected to power (default)")
    try:
        choice = input("Enter choice (1/2) [2]: ").strip()
        if choice == "1":
            logger.infow("User selected battery power")
            return PowerSource.BATTERY
        else:
            logger.infow("User selected wired power")
            return PowerSource.WIRED
    except Exception:
        logger.warnw("Error during power source selection, defaulting to wired")
        return PowerSource.WIRED
