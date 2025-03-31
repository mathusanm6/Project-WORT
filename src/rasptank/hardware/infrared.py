"""This module provides classes for interfacing with infrared sensors and emitters."""

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
        self.last_trigger_time = 0
        self.logger.debugw("IR receiver initialized", "pin", IrPins.RECEIVER.value)

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

            # Define callback function
            def ir_callback(channel):
                ir_receiver_instance.logger.debugw("IR callback triggered", "channel", channel)

                # Check if the callback is triggered too frequently
                # to avoid false positives
                now = time.time()
                if now - ir_receiver_instance.last_trigger_time < 0.3:  # 300ms cooldown
                    ir_receiver_instance.logger.debugw(
                        "Ignoring too frequent trigger",
                        "elapsed",
                        now - ir_receiver_instance.last_trigger_time,
                    )
                    return  # Ignore too-frequent triggers

                ir_receiver_instance.last_trigger_time = now
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

            # Add event detection with debounce time
            GPIO.add_event_detect(
                IrPins.RECEIVER.value,
                GPIO.FALLING,
                callback=ir_callback,
            )

            self.logger.infow("IR receiver setup complete", "pin", IrPins.RECEIVER.value)
            return True

        except Exception as e:
            self.logger.errorw("Error setting up IR receiver", "error", str(e), exc_info=True)
            return False

    def cleanup(self):
        """Clean up the IR receiver."""
        try:
            # Remove event detection
            GPIO.remove_event_detect(IrPins.RECEIVER.value)
            self.logger.infow("IR receiver GPIO cleanup complete", "pin", IrPins.RECEIVER.value)
        except Exception as e:
            self.logger.errorw("Error cleaning up IR receiver", "error", str(e), exc_info=True)
