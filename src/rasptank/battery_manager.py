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

    # File to store battery status
    BATTERY_STATE_FILE = "/tmp/rasptank_battery_state.json"

    # Default battery discharge rate (percentage per hour)
    DEFAULT_DISCHARGE_RATE = 5.0

    # Default starting battery percentage if not previously saved
    DEFAULT_BATTERY_PERCENTAGE = 100.0

    # Minimum time between state saves to prevent excessive disk writes
    SAVE_THROTTLE_SECONDS = 60

    def __init__(self, logger):
        """Initialize the battery manager."""
        self.logger = logger
        self.power_source = PowerSource.WIRED
        self.battery_percentage = self.DEFAULT_BATTERY_PERCENTAGE
        self.discharge_rate = self.DEFAULT_DISCHARGE_RATE  # % per hour
        self.last_update_time = time.time()
        self.last_save_time = 0
        self._running = False
        self._thread = None
        self._lock = threading.Lock()

        # Load saved state if available
        self._load_state()

    def start(self):
        """Start the battery management thread."""
        if self._thread is not None and self._thread.is_alive():
            return

        # Before starting the thread, make sure last_update_time is current
        with self._lock:
            self.last_update_time = time.time()

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
        """Stop the battery management thread."""
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
        """Change the power source."""
        with self._lock:
            old_source = self.power_source
            self.power_source = source

            # Always reset the timestamp when changing power source
            # This prevents incorrect discharge calculations
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
        """Reset battery to full charge (after battery replacement)."""
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
        """Get current battery percentage."""
        with self._lock:
            # If on wired power, always return 100%
            if self.power_source == PowerSource.WIRED:
                return 100.0
            return self.battery_percentage

    def _battery_monitor_thread(self):
        """Background thread to simulate battery discharge."""
        # Initialize last cycle time
        last_cycle_time = time.time()

        while self._running:
            current_time = time.time()

            # Only process if in battery mode
            if self.power_source == PowerSource.BATTERY:
                with self._lock:
                    # Calculate time since last monitoring cycle
                    # This ensures we're using the actual elapsed time
                    elapsed_seconds = current_time - last_cycle_time
                    elapsed_hours = elapsed_seconds / 3600.0

                    # Update battery percentage based on actual elapsed time
                    discharge_amount = elapsed_hours * self.discharge_rate

                    # Safeguard against time jumps
                    if discharge_amount > 10.0:  # Cap max discharge at 10% per cycle
                        discharge_amount = 0.01  # Use minimal discharge instead
                        self.logger.warnw(
                            "Large time jump detected, using minimal discharge",
                            "elapsed_seconds",
                            f"{elapsed_seconds:.1f}s",
                        )

                    # Apply the calculated discharge
                    self.battery_percentage = max(0.0, self.battery_percentage - discharge_amount)

                    # Periodically save state to disk
                    if current_time - self.last_save_time > self.SAVE_THROTTLE_SECONDS:
                        self._save_state()

                    # Log if battery is getting low
                    if self.battery_percentage < 20.0:
                        self.logger.warnw(
                            "Battery is running low",
                            "battery_percentage",
                            f"{self.battery_percentage:.1f}%",
                        )

            # Update cycle time tracking
            last_cycle_time = current_time

            # Sleep for monitoring interval
            time.sleep(10.0)

    def _save_state(self):
        """Save battery state to disk."""
        try:
            state = {
                "power_source": self.power_source.value,
                "battery_percentage": self.battery_percentage,
                "last_update_time": time.time(),  # Always save current time
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
        """Load battery state from disk if available."""
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
            # Don't use saved last_update_time, always use current time to prevent immediate discharge
            self.last_update_time = time.time()
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
