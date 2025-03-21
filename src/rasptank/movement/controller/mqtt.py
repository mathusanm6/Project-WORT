"""MQTT Movement Controller for Rasptank.

This controller receives movement commands via MQTT and translates
them into actual movement commands for the Rasptank.
"""

import json
import logging
import threading
import time
from typing import Any, Dict, Optional

from src.common.mqtt.client import MQTTClient
from src.common.mqtt.topics import MOVEMENT_COMMAND_TOPIC, MOVEMENT_STATE_TOPIC
from src.rasptank.movement.controller.base import BaseMovementController
from src.rasptank.movement.movement_api import State, ThrustDirection, TurnDirection
from src.rasptank.movement.rasptank_hardware import RasptankHardware, TurnFactor

# Configure logging
logger = logging.getLogger("MQTTMovementController")
# Ensure the logger is set to a level that will display your messages
logger.setLevel(logging.INFO)

# If the logger doesn't have handlers, add a console handler
if not logger.handlers:
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    formatter = logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)


class MQTTMovementController(BaseMovementController):
    """MQTT Movement Controller for Rasptank.

    This controller receives movement commands via MQTT and translates
    them into actual movement commands for the Rasptank.
    """

    def __init__(
        self,
        mqtt_client: Optional[MQTTClient] = None,
        broker_address: str = "192.168.1.200",
        broker_port: int = 1883,
        command_topic: str = MOVEMENT_COMMAND_TOPIC,
        state_topic: str = MOVEMENT_STATE_TOPIC,
    ):
        """Initialize the MQTT Movement Controller.

        Args:
            mqtt_client (MQTTClient, optional): Existing MQTT client to use.
                If None, a new client will be created.
            broker_address (str): MQTT broker address (only used if mqtt_client is None)
            broker_port (int): MQTT broker port (only used if mqtt_client is None)
            command_topic (str): Topic to listen for movement commands
            state_topic (str): Topic to publish movement state updates
        """
        super().__init__()

        # Initialize hardware adapter
        self.hardware = RasptankHardware()
        logger.info("RasptankHardware initialized")

        # Initialize MQTT client or use provided one
        self.mqtt_client = mqtt_client
        if self.mqtt_client is None:
            logger.info(f"Creating new MQTT client with broker: {broker_address}:{broker_port}")
            self.mqtt_client = MQTTClient(
                broker_address=broker_address,
                broker_port=broker_port,
                client_id="rasptank-movement",
            )
            self.mqtt_client.connect()
            logger.info("MQTT client connected")
        else:
            logger.info("Using provided MQTT client")

        # Set up topics
        self.command_topic = command_topic
        self.state_topic = state_topic
        logger.info(f"Command topic: {command_topic}, State topic: {state_topic}")

        # For handling timed movements
        self.timer_lock = threading.Lock()
        self.pending_timers = {}

        # Subscribe to command topic
        logger.info(f"Subscribing to command topic: {self.command_topic}")
        self.mqtt_client.subscribe(
            topic=self.command_topic,
            qos=1,  # Ensure commands are delivered at least once
            callback=self._handle_command,
        )

        # Publish initial state
        self._publish_state()

        logger.info("MQTT Movement Controller initialized and ready")

    def _handle_command(self, client, topic, payload, qos, retain):
        """Handle movement commands received via MQTT.

        Args:
            client (MQTTClient): The MQTT client that received the message
            topic (str): The topic the message was received on
            payload (str): The message payload
            qos (int): The QoS level of the message
            retain (bool): Whether the message was a retained message
        """
        logger.info(f"Received movement command on topic {topic}: {payload}")

        try:
            # Parse command message
            # Format: "<speed>;<thrust_direction>;<turn_direction>;<turn_factor>"
            parts = payload.split(";")

            if len(parts) < 3:
                logger.warning(f"Invalid command format: {payload}")
                return

            # Extract values
            speed = float(parts[0])
            thrust_dir_str = parts[1]
            turn_dir_str = parts[2]
            turn_factor = float(parts[3]) if len(parts) > 3 else TurnFactor.MODERATE.value

            logger.info(
                f"Parsed command: speed={speed}, thrust={thrust_dir_str}, turn={turn_dir_str}, factor={turn_factor}"
            )

            # Map string values to enum values
            try:
                thrust_direction = ThrustDirection(thrust_dir_str)
            except ValueError:
                logger.warning(f"Invalid thrust direction: {thrust_dir_str}")
                thrust_direction = ThrustDirection.NONE

            try:
                turn_direction = TurnDirection(turn_dir_str)
            except ValueError:
                logger.warning(f"Invalid turn direction: {turn_dir_str}")
                turn_direction = TurnDirection.NONE

            # Apply the movement
            logger.info(
                f"Applying movement: {thrust_direction.value}, {turn_direction.value}, {speed}, {turn_factor}"
            )
            self.move(thrust_direction, turn_direction, speed, turn_factor)

        except Exception as e:
            logger.error(f"Error handling movement command: {e}", exc_info=True)

    def _publish_state(self):
        """Publish the current movement state via MQTT."""
        if not self.mqtt_client.connected.is_set():
            logger.warning("MQTT client not connected, skipping state publication")
            return

        try:
            state = self.get_state()
            state_str = f"{state[State.SPEED]};{state[State.THRUST_DIRECTION]};{state[State.TURN_DIRECTION]};{state[State.TURN_FACTOR]}"

            logger.info(f"Publishing movement state: {state_str}")
            self.mqtt_client.publish(
                topic=self.state_topic,
                payload=state_str,
                qos=0,  # State updates can use QoS 0 for better performance
            )
        except Exception as e:
            logger.error(f"Error publishing movement state: {e}", exc_info=True)

    def _apply_movement(
        self,
        thrust_direction: ThrustDirection,
        turn_direction: TurnDirection,
        speed: float,
        turn_factor: float,
    ) -> Dict[State, Any]:
        # Log before applying movement
        logger.info(
            f"Sending to hardware: thrust={thrust_direction}, turn={turn_direction}, speed={speed}, turn_factor={turn_factor}"
        )

        # Apply movement to hardware
        self.hardware.move_hardware(thrust_direction, turn_direction, speed, turn_factor)

        # Log after applying movement
        logger.info("Movement applied to hardware")

        # Update and return current state
        self._state = {
            "thrust_direction": thrust_direction,
            "turn_direction": turn_direction,
            "speed": speed,
            "turn_factor": turn_factor,
        }

        return self._state

    def cleanup(self):
        """Clean up resources."""
        logger.info("Cleaning up MQTT Movement Controller resources")

        # Cancel all pending timers
        with self.timer_lock:
            for timer_id in list(self.pending_timers.keys()):
                logger.info(f"Cancelling timer {timer_id}")
                self.pending_timers[timer_id].cancel()
            self.pending_timers.clear()
            logger.info("All timers cancelled")

        # Clean up hardware resources
        logger.info("Cleaning up hardware resources")
        self.hardware.cleanup()
        logger.info("Hardware cleanup complete")

        # We don't disconnect the MQTT client here since it might be shared
        # The owning object is responsible for disconnecting the client
        logger.info("MQTT Movement Controller cleanup complete")
