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


class ReceiverState(Enum):
    """States for the IR receiver state machine."""

    READY = 0  # Ready to receive a hit
    PROCESSING = 1  # Currently processing a hit
    COOLDOWN = 2  # In cooldown period after a hit


class InfraReceiver:
    """Class for handling IR receiver events using polling approach."""

    def __init__(self, ir_receiver_logger: Logger):
        """Initialize the IR receiver."""
        self.logger = ir_receiver_logger
        self.logger.infow("Initializing IR receiver", "pin", IrPins.RECEIVER.value)

        # Setup GPIO
        GPIO.setup(IrPins.RECEIVER.value, GPIO.IN)
        self.logger.debugw("IR receiver initialized", "pin", IrPins.RECEIVER.value)

        # Initialize state management
        self.state = ReceiverState.READY
        self.cooldown_time = 2.0  # seconds to wait after a hit
        self.polling_interval = 0.01  # seconds between polls

        # Threading control
        self.running = False
        self.poll_thread = None
        self.lock = threading.Lock()

        # Store references that will be set in setup
        self.mqtt_client = None
        self.led_command_queue = None

    def _process_hit(self, shooter):
        """Process a hit from the given shooter.

        Args:
            shooter: ID of the shooter that hit this tank
        """
        self.logger.infow("Hit detected", "shooter", shooter)

        # Send a message to the main thread's queue for LED
        if self.led_command_queue:
            self.led_command_queue.put("hit")
            self.logger.debugw("LED queue notified about hit")

        # Publish the hit event to the MQTT broker
        if self.mqtt_client:
            # Game event message
            message = "hit_by_ir;" + shooter
            try:
                self.mqtt_client.publish(
                    topic=GAME_EVENT_TOPIC,
                    payload=message,
                    qos=1,
                )
                self.logger.debugw(
                    "Published hit event", "topic", GAME_EVENT_TOPIC, "payload", message
                )
            except Exception as e:
                self.logger.errorw("Failed to publish hit event", "error", str(e), exc_info=True)

            # Server message
            message = "SHOT_BY " + shooter
            try:
                self.mqtt_client.publish(
                    topic="tanks/" + TANK_ID + "/shots",
                    payload=message,
                    qos=1,
                )
                self.logger.infow(
                    "Published shot event",
                    "topic",
                    "tanks/" + TANK_ID + "/shots",
                    "payload",
                    message,
                )
            except Exception as e:
                self.logger.errorw("Failed to publish shot event", "error", str(e), exc_info=True)

    def _polling_loop(self):
        """Main polling loop that runs in a separate thread."""
        self.logger.infow("IR receiver polling thread started")
        last_state_change = time.time()

        while self.running:
            # Get current state safely
            with self.lock:
                current_state = self.state

            # State machine logic
            if current_state == ReceiverState.READY:
                # Check for IR signal
                shooter = getSignal(IrPins.RECEIVER.value, False)
                if shooter:
                    self.logger.debugw("Signal detected in READY state", "shooter", shooter)
                    with self.lock:
                        self.state = ReceiverState.PROCESSING
                        last_state_change = time.time()

                    # Process the hit
                    self._process_hit(shooter)

                    # Move to cooldown state
                    with self.lock:
                        self.state = ReceiverState.COOLDOWN
                        last_state_change = time.time()

            elif current_state == ReceiverState.PROCESSING:
                # Should be brief - just in case we get stuck
                if time.time() - last_state_change > 0.5:  # 500ms max processing time
                    with self.lock:
                        self.state = ReceiverState.COOLDOWN
                        last_state_change = time.time()

            elif current_state == ReceiverState.COOLDOWN:
                # Check if cooldown period has elapsed
                if time.time() - last_state_change > self.cooldown_time:
                    self.logger.debugw("Cooldown completed, returning to READY state")
                    with self.lock:
                        self.state = ReceiverState.READY

            # Sleep to avoid hammering the CPU
            time.sleep(self.polling_interval)

    def setup_ir_receiver(self, client, led_command_queue):
        """Set up the IR receiver using polling in a separate thread.

        Args:
            client: MQTT client for publishing hit events
            led_command_queue: Queue for LED commands

        Returns:
            bool: True if setup was successful, False otherwise
        """
        try:
            # Store references
            self.mqtt_client = client
            self.led_command_queue = led_command_queue

            # Ensure we're not already running
            if self.running:
                self.logger.warnw("IR receiver is already running, stopping first")
                self.cleanup()

            # Start the polling thread
            self.running = True
            self.state = ReceiverState.READY
            self.poll_thread = threading.Thread(target=self._polling_loop)
            self.poll_thread.daemon = True  # Thread will exit when main program exits
            self.poll_thread.start()

            self.logger.infow("IR receiver setup complete", "pin", IrPins.RECEIVER.value)
            return True

        except Exception as e:
            self.logger.errorw("Error setting up IR receiver", "error", str(e), exc_info=True)
            self.running = False
            return False

    def cleanup(self):
        """Clean up the IR receiver."""
        try:
            # Signal the thread to stop
            self.running = False

            # Wait for the thread to exit (with timeout)
            if self.poll_thread and self.poll_thread.is_alive():
                self.poll_thread.join(timeout=1.0)

            self.logger.infow("IR receiver cleanup complete", "pin", IrPins.RECEIVER.value)
        except Exception as e:
            self.logger.errorw("Error cleaning up IR receiver", "error", str(e), exc_info=True)
