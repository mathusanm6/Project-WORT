"""MQTT Movement Controller for Rasptank.

This controller receives movement commands via MQTT and translates
them into actual movement commands for the Rasptank.
"""

import threading
from typing import Optional

# Import from src.common
from src.common.constants.movement import MOVEMENT_COMMAND_TOPIC, MOVEMENT_STATE_TOPIC
from src.common.enum.movement import (
    CurvedTurnRate,
    SpeedMode,
    ThrustDirection,
    TurnDirection,
    TurnType,
)
from src.common.logging.decorators import log_function_call

# Import from logging system
from src.common.logging.logger_api import Logger
from src.common.mqtt.client import MQTTClient

# Import from src.rasptank
from src.rasptank.hardware.hardware_main import RasptankHardware
from src.rasptank.movement.controller.base import BaseMovementController
from src.rasptank.movement.movement_api import State


class MQTTMovementController(BaseMovementController):
    """MQTT Movement Controller for Rasptank.

    This controller receives movement commands via MQTT and translates
    them into actual movement commands for the Rasptank.
    """

    def __init__(
        self,
        movement_logger: Logger,
        hardware: RasptankHardware,
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

        # Create a logger for this component
        self.logger = movement_logger

        # Hardware-specific implementation
        self.hardware = hardware

        # Initialize MQTT client or use provided one
        self.mqtt_client = mqtt_client
        if self.mqtt_client is None:
            mqtt_logger = self.logger.with_component("mqtt")
            self.mqtt_client = MQTTClient(
                mqtt_logger=mqtt_logger,
                broker_address=broker_address,
                broker_port=broker_port,
                client_id="rasptank-movement",
            )
            self.mqtt_client.connect()
        else:
            self.logger.infow("Using provided MQTT client", "client_id", self.mqtt_client.client_id)

        # Set up topics
        self.command_topic = command_topic
        self.state_topic = state_topic
        self.logger.debugw(
            "Controller configuration", "command_topic", command_topic, "state_topic", state_topic
        )

        # For handling timed movements
        self.timer_lock = threading.Lock()
        self.pending_timers = {}

        # Subscribe to command topic
        self.logger.infow("Subscribing to command topic", "topic", self.command_topic)
        self.mqtt_client.subscribe(
            topic=self.command_topic,
            qos=0,  # QoS 0 for movement command messages
            callback=self._handle_command,
        )

        # Publish initial state
        self._publish_state()

    def _handle_command(self, client, topic, payload, qos, retain):
        """Handle movement commands received via MQTT.

        Args:
            client (MQTTClient): The MQTT client that received the message
            topic (str): The topic the message was received on
            payload (str): The message payload
            qos (int): The QoS level of the message
            retain (bool): Whether the message was a retained message
        """
        self.logger.debugw("Received movement command", "topic", topic, "payload", payload)

        try:
            # Parse command message
            # Format: "<thrust_direction>;<turn_direction>;<turn_type>;<speed_mode>;<curved_turn_rate>"
            parts = payload.split(";")

            if len(parts) < 5:
                self.logger.warnw("Invalid command format", "payload", payload, "expected_parts", 5)
                return

            # Extract values
            thrust_dir_str = parts[0]
            turn_dir_str = parts[1]
            turn_type_str = parts[2]
            speed_value = int(parts[3])
            curved_turn_rate_float = float(parts[4])

            self.logger.debugw(
                "Parsed command",
                "thrust_direction",
                thrust_dir_str,
                "turn_direction",
                turn_dir_str,
                "turn_type",
                turn_type_str,
                "speed_value",
                speed_value,
                "curved_turn_rate",
                curved_turn_rate_float,
            )

            # Map string values to enum values
            try:
                thrust_direction = ThrustDirection(thrust_dir_str)
            except ValueError:
                self.logger.warnw("Invalid thrust direction", "value", thrust_dir_str)
                thrust_direction = ThrustDirection.NONE

            try:
                turn_direction = TurnDirection(turn_dir_str)
            except ValueError:
                self.logger.warnw("Invalid turn direction", "value", turn_dir_str)
                turn_direction = TurnDirection.NONE

            try:
                turn_type = TurnType(turn_type_str)
            except ValueError:
                self.logger.warnw("Invalid turn type", "value", turn_type_str)
                turn_type = TurnType.NONE

            try:
                speed_mode = SpeedMode(speed_value)
            except ValueError:
                self.logger.warnw("Invalid speed value", "value", speed_value)
                speed_mode = SpeedMode.STOP

            try:
                curved_turn_rate = CurvedTurnRate(curved_turn_rate_float)
            except ValueError:
                self.logger.warnw("Invalid curved turn rate", "value", curved_turn_rate_float)
                curved_turn_rate = CurvedTurnRate.NONE

            # Apply the movement
            self.logger.debugw(
                "Applying movement",
                "thrust_direction",
                thrust_direction.value,
                "turn_direction",
                turn_direction.value,
                "turn_type",
                turn_type.value,
                "speed_mode",
                speed_mode.value,
                "curved_turn_rate",
                curved_turn_rate.value,
            )
            self.move(thrust_direction, turn_direction, turn_type, speed_mode, curved_turn_rate)

        except Exception as e:
            self.logger.errorw("Error handling movement command", "error", str(e), exc_info=True)

    def _publish_state(self):
        """Publish the current movement state via MQTT."""
        if not self.mqtt_client.connected.is_set():
            self.logger.warnw("MQTT client not connected, skipping state publication")
            return

        try:
            state = self.get_state()
            # Format: "<thrust_direction>;<turn_direction>;<turn_type>;<speed_mode>;<curved_turn_rate>"
            state_str = f"{state.thrust_direction.value};{state.turn_direction.value};{state.turn_type.value};{state.speed_mode.value};{state.curved_turn_rate.value}"

            self.logger.debugw("Publishing movement state", "state", state_str)
            self.mqtt_client.publish(
                topic=self.state_topic,
                payload=state_str,
                qos=0,  # QoS 0 for movement state messages
            )
        except Exception as e:
            self.logger.errorw("Error publishing movement state", "error", str(e), exc_info=True)

    # Override _apply_movement method from BaseMovementController
    @log_function_call()
    def _apply_movement(
        self,
        thrust_direction: ThrustDirection,
        turn_direction: TurnDirection,
        turn_type: TurnType,
        speed_mode: SpeedMode,
        curved_turn_rate: CurvedTurnRate,
    ) -> State:
        # Log before applying movement
        self.logger.debugw(
            "Sending to hardware",
            "thrust_direction",
            thrust_direction.value,
            "turn_direction",
            turn_direction.value,
            "turn_type",
            turn_type.value,
            "speed_mode",
            speed_mode.value,
            "curved_turn_rate",
            curved_turn_rate.value,
        )

        # Apply movement to hardware
        self.hardware.move_rasptank_hardware(
            thrust_direction, turn_direction, turn_type, speed_mode, curved_turn_rate
        )

        # Update and return current state
        self._state = State(
            thrust_direction=thrust_direction,
            turn_direction=turn_direction,
            turn_type=turn_type,
            speed_mode=speed_mode,
            curved_turn_rate=curved_turn_rate,
        )

        # Publish state update
        self._publish_state()

        return self._state

    def cleanup(self):
        """Clean up resources."""
        self.logger.infow("Cleaning up MQTT Movement Controller resources")

        # Cancel all pending timers
        with self.timer_lock:
            for timer_id in list(self.pending_timers.keys()):
                self.logger.debugw("Cancelling timer", "timer_id", timer_id)
                self.pending_timers[timer_id].cancel()
            self.pending_timers.clear()
            self.logger.debugw("All timers cancelled")

        # We don't disconnect the MQTT client here since it might be shared
        # The owning object is responsible for disconnecting the client
        self.logger.infow("MQTT Movement Controller cleanup complete")
