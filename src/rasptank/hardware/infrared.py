"""This module provides classes for interfacing with infrared sensors and emitters."""

import threading
import time
import uuid
from enum import Enum

from RPi import GPIO

# Import from src.common
from src.common.constants.game import GAME_EVENT_TOPIC
from src.common.logging.logger_api import Logger, LogLevel
from src.rasptank.constants import TANK_ID

# src.rasptank
from src.rasptank.hardware.infra_lib import IRBlast, getSignal


class IrPins(Enum):
    """Pin numbers for the infrared emitter and receiver."""

    EMITTER = 23
    RECEIVER = 22


class InfraEmitter:
    """Class for controlling the IR emitter."""

    def __init__(self, ir_emitter_logger: Logger):
        """Initialize the IR emitter."""
        self.logger = ir_emitter_logger
        self.logger.infow("Initializing IR emitter", "pin", IrPins.EMITTER.value)

        GPIO.setup(IrPins.EMITTER.value, GPIO.OUT)
        self.logger.debugw("IR emitter initialized", "pin", IrPins.EMITTER.value)

    def blast(self, verbose=False):
        """Blast an IR signal.

        Args:
            verbose (bool): Whether to log verbose information

        Returns:
            bool: True if the blast was successful, False otherwise
        """
        self.logger.debugw("Blasting IR signal", "verbose", verbose, "node_id", uuid.getnode())
        return IRBlast(uuid.getnode(), "LASER", verbose=verbose)

    def cleanup(self):
        """Clean up the IR emitter."""
        self.logger.infow("IR emitter GPIO cleanup complete", "pin", IrPins.EMITTER.value)


class InfraReceiver:
    """Class for handling IR receiver events."""

    def __init__(self, ir_receiver_logger: Logger):
        """Initialize the IR receiver."""
        self.logger = ir_receiver_logger
        self.logger.infow("Initializing IR receiver", "pin", IrPins.RECEIVER.value)

        GPIO.setup(IrPins.RECEIVER.value, GPIO.IN)
        self.logger.debugw("IR receiver initialized", "pin", IrPins.RECEIVER.value)

        # Initialize last hit time for debouncing
        self.last_hit_time = 0
        # Set the debounce interval (in seconds) - increased for greater stability
        self.debounce_interval = 2.0  # Adjusted to 2 seconds
        # Create a lock for thread safety
        self.ir_lock = threading.Lock()
        # Flag to disable IR processing temporarily after a hit
        self.ir_disabled = False
        # Timer for re-enabling IR
        self.disable_timer = None

    def _disable_ir_temporarily(self):
        """Temporarily disable IR processing to avoid multiple triggers."""
        with self.ir_lock:
            self.ir_disabled = True

        # Set a timer to re-enable IR after the debounce period
        if self.disable_timer:
            self.disable_timer.cancel()

        self.disable_timer = threading.Timer(self.debounce_interval, self._enable_ir)
        self.disable_timer.daemon = True
        self.disable_timer.start()

    def _enable_ir(self):
        """Re-enable IR processing after the debounce period."""
        with self.ir_lock:
            self.ir_disabled = False
            self.logger.debugw("IR receiver re-enabled after debounce period")

    def setup_ir_receiver(self, client, led_command_queue):
        """Set up the IR receiver using interrupts for detecting hits.

        Args:
            client: MQTT client for publishing hit events
            led_command_queue: Queue for LED commands

        Returns:
            bool: True if setup was successful, False otherwise
        """
        try:
            # Store a reference to self for the callback closure
            ir_receiver_instance = self

            # Define callback function with better debounce handling
            def ir_callback(channel):
                # Log only if not in a blocked state to reduce log spam
                with ir_receiver_instance.ir_lock:
                    if ir_receiver_instance.ir_disabled:
                        return

                ir_receiver_instance.logger.debugw("IR callback triggered", "channel", channel)

                # Get current time for debounce checking
                current_time = time.time()
                elapsed = current_time - ir_receiver_instance.last_hit_time

                # Check if we should ignore this trigger due to debounce
                if elapsed < ir_receiver_instance.debounce_interval:
                    ir_receiver_instance.logger.debugw(
                        "Ignoring too frequent trigger", "elapsed", elapsed
                    )
                    return

                # Immediately disable IR to prevent further processing during this hit
                ir_receiver_instance._disable_ir_temporarily()

                # Update the last hit time
                ir_receiver_instance.last_hit_time = current_time

                # Process the signal
                shooter = getSignal(channel, False)

                if shooter:
                    ir_receiver_instance.logger.infow("Hit detected", "shooter", shooter)

                    # Send a message to the main thread's queue
                    if led_command_queue:
                        led_command_queue.put("hit")
                        ir_receiver_instance.logger.debugw("LED queue notified about hit")

                    # Publish the hit event to the MQTT broker
                    if client:
                        message = "hit_by_ir;" + shooter
                        try:
                            client.publish(
                                topic=GAME_EVENT_TOPIC,
                                payload=message,
                                qos=1,
                            )
                            ir_receiver_instance.logger.debugw(
                                "Published hit event", "topic", GAME_EVENT_TOPIC, "payload", message
                            )
                        except Exception as e:
                            ir_receiver_instance.logger.errorw(
                                "Failed to publish hit event", "error", str(e), exc_info=True
                            )

                        # Send server
                        message = "SHOT_BY " + shooter
                        try:
                            client.publish(
                                topic="tanks/" + TANK_ID + "/shots",
                                payload=message,
                                qos=1,
                            )
                            ir_receiver_instance.logger.infow(
                                "Published shot event",
                                "topic",
                                "tanks/" + TANK_ID + "/shots",
                                "payload",
                                message,
                            )
                        except Exception as e:
                            ir_receiver_instance.logger.errorw(
                                "Failed to publish shot event", "error", str(e), exc_info=True
                            )

            # Remove any existing event detection first (in case of reinitializing)
            try:
                GPIO.remove_event_detect(IrPins.RECEIVER.value)
            except:
                pass  # Ignore if no previous event detection

            # Add event detection with much higher bouncetime
            GPIO.add_event_detect(
                IrPins.RECEIVER.value,
                GPIO.FALLING,
                callback=ir_callback,
                bouncetime=500,  # 500ms hardware debounce - significantly higher
            )

            self.logger.infow(
                "IR receiver setup complete with enhanced debounce protection",
                "pin",
                IrPins.RECEIVER.value,
                "debounce_interval",
                self.debounce_interval,
                "bouncetime",
                500,
            )
            return True

        except Exception as e:
            self.logger.errorw("Error setting up IR receiver", "error", str(e), exc_info=True)
            return False

    def cleanup(self):
        """Clean up the IR receiver."""
        try:
            # Cancel any pending timer
            if self.disable_timer:
                self.disable_timer.cancel()

            # Remove event detection
            GPIO.remove_event_detect(IrPins.RECEIVER.value)
            self.logger.infow("IR receiver GPIO cleanup complete", "pin", IrPins.RECEIVER.value)
        except Exception as e:
            self.logger.errorw("Error cleaning up IR receiver", "error", str(e), exc_info=True)
