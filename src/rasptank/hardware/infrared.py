"""This module provides classes for interfacing with infrared sensors and emitters."""

import logging
import threading
import time
import uuid
from enum import Enum

import RPi.GPIO as GPIO

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

        # IR polling thread
        self.ir_polling_active = True
        self.ir_polling_thread = None

    def poll_ir_receiver(self, pin, client, led_queue=None):
        """Continuously poll the IR receiver for signals"""
        logging.info(f"Starting IR receiver polling on pin {pin}...")

        while self.ir_polling_active:
            try:
                # Always ensure GPIO mode is set
                try:
                    GPIO.setmode(GPIO.BCM)
                except Exception:
                    # Mode might already be set, which is fine
                    pass

                shooter = getSignal(pin, True)
                time.sleep(0.01)  # Small delay to prevent CPU overload

                if not shooter:
                    continue

                logging.info(f"Hit detected from shooter: {shooter}")

                # Send a message to the main thread's queue
                if led_queue:
                    led_queue.put("hit")
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
                        # Client might be disconnected during shutdown
                        if "disconnected" in str(e).lower():
                            self.ir_polling_active = False

                # Wait a bit before checking again to avoid multiple triggers
                time.sleep(0.5)

            except Exception as e:
                logging.error(f"Error in IR polling: {e}")
                # If we get persistent GPIO errors, it likely means
                # we're shutting down, so stop polling
                if "GPIO" in str(e) and not self.ir_polling_active:
                    break
                time.sleep(0.1)

    def setup_ir_receiver(self, client, led_command_queue):
        """Set up the IR receiver for detecting hits."""
        try:
            # Start a separate thread for continuous polling
            self.ir_polling_thread = threading.Thread(
                target=self.poll_ir_receiver,
                args=(IrPins.RECEIVER.value, client, led_command_queue),
                daemon=True,
            )
            self.ir_polling_thread.start()
            return True
        except Exception as e:
            logging.error(f"Error setting up IR receiver: {e}")
            return False

    def cleanup(self):
        """Clean up the IR receiver."""
        # Stop IR polling thread explicitly
        self.ir_polling_active = False
        if self.ir_polling_thread and self.ir_polling_thread.is_alive():
            self.ir_polling_thread.join(timeout=1.0)
            logging.info("IR polling thread stopped")

        GPIO.cleanup(IrPins.RECEIVER.value)
        logging.info("IR receiver GPIO cleanup complete")
