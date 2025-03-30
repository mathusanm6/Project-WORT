"""
Battery management module for Rasptank with extreme discharge rate.
This module forces battery to drain completely in about 5 seconds.
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

    # Discharge settings
    DRAIN_SECONDS = 5.0  # Completely drain in 5 seconds
    DEFAULT_BATTERY_PERCENTAGE = 100.0

    # Minimum time between state saves to prevent excessive disk writes
    SAVE_THROTTLE_SECONDS = 60

    def __init__(self, logger):
        """Initialize the battery manager."""
        self.logger = logger
        self.power_source = PowerSource.WIRED
        self.battery_percentage = self.DEFAULT_BATTERY_PERCENTAGE
        self.start_discharge_time = None  # When we started discharging
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

        self._running = True
        self._thread = threading.Thread(target=self._battery_monitor_thread, daemon=True)
        self._thread.start()
        self.logger.infow(
            "EXTREME battery management system started",
            "power_source",
            self.power_source.value,
            "battery_percentage",
            f"{self.battery_percentage:.1f}%",
            "drain_time",
            f"{self.DRAIN_SECONDS} seconds",
        )

    def stop(self):
        """Stop the battery management thread."""
        self._running = False

        # Save the state before shutting down
        self._save_state()

        # No need to join the thread since it's a daemon thread
        # The thread will be terminated when the program exits
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

            # If switching to battery, record the start time
            if source == PowerSource.BATTERY and old_source != PowerSource.BATTERY:
                self.start_discharge_time = time.time()
                self.logger.infow(
                    "Starting extreme battery discharge timer",
                    "drain_seconds",
                    self.DRAIN_SECONDS,
                )

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
            if self.power_source == PowerSource.BATTERY:
                self.start_discharge_time = time.time()
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

            # If we're on battery power, calculate percentage based on elapsed time
            if self.start_discharge_time is not None:
                elapsed_seconds = time.time() - self.start_discharge_time
                percentage = max(0.0, 100.0 * (1.0 - (elapsed_seconds / self.DRAIN_SECONDS)))

                # Update the stored percentage
                self.battery_percentage = percentage

                # If we've completely drained, log it
                if percentage <= 0.0 and self.battery_percentage > 0.0:
                    self.logger.warnw(
                        "Battery completely drained",
                        "elapsed_seconds",
                        f"{elapsed_seconds:.1f}",
                    )

                return percentage
            return self.battery_percentage

    def _battery_monitor_thread(self):
        """Background thread to check battery status and log it."""
        last_percentage = 100.0
        while self._running:
            try:
                if self.power_source == PowerSource.BATTERY:
                    with self._lock:
                        # Get current battery percentage (this will update it too)
                        percentage = self.get_battery_percentage()

                        # Only log if the percentage has changed significantly
                        if last_percentage - percentage >= 5.0:
                            self.logger.infow(
                                "Battery discharging",
                                "battery_percentage",
                                f"{percentage:.1f}%",
                                "elapsed_seconds",
                                f"{time.time() - self.start_discharge_time:.1f}",
                            )
                            last_percentage = percentage

                        # Log progress at certain thresholds
                        if percentage <= 80.0 and percentage > 75.0:
                            self.logger.infow(
                                "Battery at ~80%",
                                "elapsed_seconds",
                                f"{time.time() - self.start_discharge_time:.1f}",
                            )
                        elif percentage <= 50.0 and percentage > 45.0:
                            self.logger.infow(
                                "Battery at ~50%",
                                "elapsed_seconds",
                                f"{time.time() - self.start_discharge_time:.1f}",
                            )
                        elif percentage <= 20.0 and percentage > 15.0:
                            self.logger.warnw(
                                "Battery at ~20%",
                                "elapsed_seconds",
                                f"{time.time() - self.start_discharge_time:.1f}",
                            )
                        elif percentage <= 10.0 and percentage > 5.0:
                            self.logger.warnw(
                                "Battery at ~10%",
                                "elapsed_seconds",
                                f"{time.time() - self.start_discharge_time:.1f}",
                            )
                        elif percentage <= 0.1:
                            # Just in case we haven't logged it yet
                            self.logger.warnw(
                                "Battery depleted",
                                "elapsed_seconds",
                                f"{time.time() - self.start_discharge_time:.1f}",
                            )

                        # Periodically save state to disk
                        current_time = time.time()
                        if current_time - self.last_save_time > self.SAVE_THROTTLE_SECONDS:
                            self._save_state()
            except Exception as e:
                # Catch any exceptions to prevent thread from dying
                self.logger.errorw("Error in battery monitor thread", "error", str(e))

            # Check every 0.1 seconds for more responsive updates
            time.sleep(0.1)

    def _save_state(self):
        """Save battery state to disk."""
        try:
            state = {
                "power_source": self.power_source.value,
                "battery_percentage": self.battery_percentage,
                "start_discharge_time": self.start_discharge_time,
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

            # Don't restore the discharge start time - we want to start fresh
            self.start_discharge_time = (
                None if self.power_source == PowerSource.WIRED else time.time()
            )

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
    """Prompt user to select power source at startup."""
    print("\n===== Rasptank Power Source Configuration =====")
    print("Is the Rasptank running on batteries or connected to power?")
    print("1. Running on batteries (EXTREME 5-second discharge)")
    print("2. Connected to power (default)")

    try:
        choice = input("Enter choice (1/2) [2]: ").strip()
        if choice == "1":
            logger.infow("User selected battery power with extreme discharge")
            return PowerSource.BATTERY
        else:
            logger.infow("User selected wired power")
            return PowerSource.WIRED
    except Exception:
        logger.warnw("Error during power source selection, defaulting to wired")
        return PowerSource.WIRED
