"""This module provides classes for interfacing with infrared sensors and emitters."""

import logging
import threading
import time
import uuid
from enum import Enum

from RPi import GPIO

# Import from src.common
from src.common.constants.game import GAME_EVENT_TOPIC

# src.rasptank
from src.rasptank.hardware.infra_lib import IRBlast, getSignal


class IrPins(Enum):
    """Pin numbers for the infrared emitter and receiver."""

    EMITTER = 23
    RECEIVER = 22


class InfraEmitter:
    def __init__(self):
        GPIO.setup(IrPins.EMITTER.value, GPIO.OUT)

    def blast(self, verbose=False):
        """Blast an IR signal."""
        return IRBlast(uuid.getnode(), "LASER", verbose=verbose)

    def cleanup(self):
        """Clean up the IR emitter."""
        GPIO.cleanup(IrPins.EMITTER.value)
        logging.info("IR emitter GPIO cleanup complete")


class InfraReceiver:
    def __init__(self):
        GPIO.setup(IrPins.RECEIVER.value, GPIO.IN)
        self.last_trigger_time = 0

    def setup_ir_receiver(self, client, led_command_queue):
        """Set up the IR receiver using interrupts for detecting hits."""
        try:
            # Define callback function
            def ir_callback(channel):
                logging.debug(f"IR callback triggered on channel {channel}")
                # Check if the callback is triggered too frequently
                # to avoid false positives
                now = time.time()
                if now - self.last_trigger_time < 0.3:  # 300ms cooldown
                    return  # Ignore too-frequent triggers
                self.last_trigger_time = now

                shooter = getSignal(channel, False)
                if shooter:
                    logging.info(f"Hit detected from shooter: {shooter}")

                    # Send a message to the main thread's queue
                    if led_command_queue:
                        led_command_queue.put("hit")
                        logging.info("LED queue notified about hit")

                    # Publish the hit event to the MQTT broker
                    if client:
                        message = "hit_by_ir;" + shooter
                        try:
                            client.publish(
                                topic=GAME_EVENT_TOPIC,
                                payload=message,
                                qos=1,
                            )
                        except Exception as e:
                            logging.error(f"Failed to publish hit event: {e}")

            # Add event detection with debounce time
            GPIO.add_event_detect(
                IrPins.RECEIVER.value,
                GPIO.FALLING,
                callback=ir_callback,
            )

            return True
        except Exception as e:
            logging.error(f"Error setting up IR receiver: {e}")
            return False

    def cleanup(self):
        """Clean up the IR receiver."""
        try:
            # Remove event detection
            GPIO.remove_event_detect(IrPins.RECEIVER.value)
            GPIO.cleanup(IrPins.RECEIVER.value)
            logging.info("IR receiver GPIO cleanup complete")
        except Exception as e:
            logging.error(f"Error cleaning up IR receiver: {e}")
