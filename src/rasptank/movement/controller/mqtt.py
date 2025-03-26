"""MQTT Movement Controller for Rasptank.

This controller receives movement commands via MQTT and translates
them into actual movement commands for the Rasptank.
"""

import logging
import threading
from typing import Optional

# Import from src.common
from src.common.enum.movement import (
    CurvedTurnRate,
    SpeedMode,
    ThrustDirection,
    TurnDirection,
    TurnType,
)
from src.common.mqtt.client import MQTTClient
from src.common.mqtt.topics import MOVEMENT_COMMAND_TOPIC, MOVEMENT_STATE_TOPIC

# Import from src.rasptank
from src.rasptank.movement.controller.base import BaseMovementController
from src.rasptank.movement.movement_api import State
from src.rasptank.movement.rasptank_hardware import RasptankHardware

# Configure logging
logger = logging.getLogger("MQTTMovementController")
logger.setLevel(logging.INFO)  # Ensure the logger is set to a level that will display your messages

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
        super().__init__()  # Initialize the base class (BaseMovementController) with default state

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
            qos=0,  # QoS 0 for movement command messages
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
            # Format: "<thrust_direction>;<turn_direction>;<turn_type>;<speed_mode>;<curved_turn_rate>"
            parts = payload.split(";")

            if len(parts) < 5:
                logger.warning(f"Invalid command format: {payload}")
                return

            # Extract values
            thrust_dir_str = parts[0]
            turn_dir_str = parts[1]
            turn_type_str = parts[2]
            speed_value = int(parts[3])
            curved_turn_rate_float = float(parts[4])

            logger.info(
                f"Parsed command: thrust_direction={thrust_dir_str}, turn_direction={turn_dir_str}, turn_type={turn_type_str}, speed_value={speed_value}, curved_turn_rate={curved_turn_rate_float}"
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

            try:
                turn_type = TurnType(turn_type_str)
            except ValueError:
                logger.warning(f"Invalid turn type: {turn_type_str}")
                turn_type = TurnType.NONE

            try:
                speed_mode = SpeedMode(speed_value)
            except ValueError:
                logger.warning(f"Invalid speed value: {speed_value}")
                speed_mode = SpeedMode.STOP

            try:
                curved_turn_rate = CurvedTurnRate(curved_turn_rate_float)
            except ValueError:
                logger.warning(f"Invalid curved turn rate: {curved_turn_rate_float}")
                curved_turn_rate = CurvedTurnRate.NONE

            # Apply the movement
            logger.info(
                f"Applying movement: thrust_direction={thrust_direction}, turn_direction={turn_direction}, turn_type={turn_type}, speed_mode={speed_mode}, curved_turn_rate={curved_turn_rate}"
            )
            self.move(thrust_direction, turn_direction, turn_type, speed_mode, curved_turn_rate)

        except Exception as e:
            logger.error(f"Error handling movement command: {e}", exc_info=True)

    def _publish_state(self):
        """Publish the current movement state via MQTT."""
        if not self.mqtt_client.connected.is_set():
            logger.warning("MQTT client not connected, skipping state publication")
            return

        try:
            state = self.get_state()
            # Format: "<thrust_direction>;<turn_direction>;<turn_type>;<speed_mode>;<curved_turn_rate>"
            state_str = f"{state.thrust_direction};{state.turn_direction};{state.turn_type};{state.speed_mode};{state.curved_turn_rate}"

            logger.info(f"Publishing movement state: {state_str}")
            self.mqtt_client.publish(
                topic=self.state_topic,
                payload=state_str,
                qos=0,  # QoS 0 for movement state messages
            )
        except Exception as e:
            logger.error(f"Error publishing movement state: {e}", exc_info=True)

    # Override _apply_movement method from BaseMovementController
    def _apply_movement(
        self,
        thrust_direction: ThrustDirection,
        turn_direction: TurnDirection,
        turn_type: TurnType,
        speed_mode: SpeedMode,
        curved_turn_rate: CurvedTurnRate,
    ) -> State:
        # Log before applying movement
        logger.info(
            f"Sending to hardware: thrust_direction={thrust_direction}, turn_direction={turn_direction}, turn_type={turn_type}, speed_mode={speed_mode}, curved_turn_rate={curved_turn_rate}"
        )

        # Apply movement to hardware
        self.hardware.move_hardware(
            thrust_direction, turn_direction, turn_type, speed_mode, curved_turn_rate
        )

        # Log after applying movement
        logger.info("Movement applied to hardware")

        # Update and return current state
        self._state = State(
            thrust_direction=thrust_direction,
            turn_direction=turn_direction,
            turn_type=turn_type,
            speed_mode=speed_mode,
            curved_turn_rate=curved_turn_rate,
        )

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
