"""
RaspTank Movement Adapter with improved separation of concerns.

This adapter converts raw controller inputs into movement commands
compatible with the RaspTank hardware implementation.
"""

import logging
import math
import time
from typing import Any, Callable, Dict, Optional

# Import from the new modular controller structure
from src.dashboard.game_controller.dualsense_controller import DualSenseController, Speed
from src.dashboard.game_controller.events import (
    ButtonType,
    DPadDirection,
    JoystickType,
    TriggerType,
)
from src.rasptank.movement.movement_api import ThrustDirection, TurnDirection

# Configure logging
logger = logging.getLogger(__name__)

# Movement constants

DEAD_ZONE = 0.20  # Joystick dead zone (increased to 0.2)
TURN_THRESHOLD = 0.80  # Threshold for sharp turns
VERTICAL_THRESHOLD = 0.20  # Vertical threshold for Joystick x
HORIZONTAL_THRESHOLD = 0.20  # Horizontal threshold for Joystick y

# Turn factors
MODERATE_TURN_FACTOR = 0.60  # Moderate turn factor
SHARP_TURN_FACTOR = 1.0  # Sharp turn factor

# Speed mode color mapping
SPEED_MODE_COLORS = {
    0: (0, 255, 0),  # Low speed: Green
    1: (255, 255, 0),  # Medium speed: Yellow
    2: (255, 0, 0),  # High speed: Red
}


class ControllerMovementAdapter:
    """
    Adapter that converts controller inputs into movement commands
    compatible with the RaspTank hardware implementation.

    Responsibilities:
    - Convert raw joystick input to thrust and turn directions
    - Handle speed control based on button presses (L1 decrease, R1 increase)
    - Manage turning logic
    - Send movement commands via callbacks
    - Provide haptic and LED feedback based on movement state
    """

    def __init__(
        self,
        controller: DualSenseController,
        on_movement_command: Optional[Callable] = None,
        on_action_command: Optional[Callable] = None,
    ):
        """Initialize the RaspTank movement adapter.

        Args:
            controller: The DualSense controller to adapt
            on_movement_command: Callback for movement commands
                Function signature: callback(speed, thrust_direction, turn_direction, turn_factor)
            on_action_command: Callback for action commands (not used for movement)
                Function signature: callback(action_name, action_value)
        """
        self.controller = controller
        self.on_movement_command = on_movement_command
        self.on_action_command = on_action_command

        # Check if controller has feedback capabilities
        self.has_feedback = hasattr(controller, "has_feedback") and controller.has_feedback
        if self.has_feedback:
            logger.info("DualSense feedback features enabled for movement adapter")
        else:
            logger.info("DualSense feedback features not available")

        # Register as handlers for the controller's callbacks
        self.controller.on_button_event = self._handle_button_event
        self.controller.on_joystick_event = self._handle_joystick_event
        self.controller.on_trigger_event = self._handle_trigger_event
        self.controller.on_dpad_event = self._handle_dpad_event

        # Raw joystick input values
        self.joystick_left_x = 0.0
        self.joystick_left_y = 0.0
        self.joystick_right_x = 0.0
        self.joystick_right_y = 0.0

        # Speed control (changed default to LOW speed)
        self.current_speed_mode = 0  # 0=low, 1=medium, 2=high
        self.speed_values = [Speed.LOW.value, Speed.MEDIUM.value, Speed.HIGH.value]

        # Last movement command sent
        self.last_movement = None

        # Set initial LED color based on speed mode if feedback available
        if self.has_feedback:
            self.controller.set_led_color(*SPEED_MODE_COLORS[self.current_speed_mode])

        logger.info("RaspTank Movement Adapter initialized with improved control scheme")
        logger.info(
            f"Initial speed mode: {self.current_speed_mode} (LOW - {self.speed_values[self.current_speed_mode]}%)"
        )

    def _handle_button_event(self, button_name, pressed):
        """
        Handle raw button events from the controller.

        Args:
            button_name (str): Name of the button
            pressed (bool): Whether the button is pressed
        """
        # Print raw button event for debugging
        logger.debug(f"Button event: {button_name} {'pressed' if pressed else 'released'}")

        # Handle speed control with L1 button (decrease speed)
        if button_name == "L1" and pressed:
            # Print current speed mode for debugging
            logger.info(f"L1 pressed. Current speed mode before: {self.current_speed_mode}")

            # Decrease speed mode (without wrap-around)
            if self.current_speed_mode > 0:
                self.current_speed_mode -= 1
                logger.info(
                    f"Speed decreased to mode {self.current_speed_mode} ({self.speed_values[self.current_speed_mode]}%)"
                )

                # Update LED color based on new speed mode and rumble
                self.controller.speed_changed(*SPEED_MODE_COLORS[self.current_speed_mode])

                # Update movement with new speed if we're currently moving
                if self.last_movement and not (
                    self.last_movement[1] is ThrustDirection.NONE
                    and self.last_movement[2] is TurnDirection.NONE
                ):
                    self._process_joystick_to_movement()
            else:
                logger.info("Already at the lowest speed mode")
                self.controller.speed_out_of_bound(*SPEED_MODE_COLORS[self.current_speed_mode])

            logger.info(f"L1 pressed. Speed mode after: {self.current_speed_mode}")

        # Handle speed control with R1 button (increase speed)
        elif button_name == "R1" and pressed:
            # Print current speed mode for debugging
            logger.info(f"R1 pressed. Current speed mode before: {self.current_speed_mode}")

            # Increase speed mode (without wrap-around)
            if self.current_speed_mode < len(self.speed_values) - 1:
                self.current_speed_mode += 1
                logger.info(
                    f"Speed increased to mode {self.current_speed_mode} ({self.speed_values[self.current_speed_mode]}%)"
                )

                # Update LED color based on new speed mode and rumble
                self.controller.speed_changed(*SPEED_MODE_COLORS[self.current_speed_mode])

                # Update movement with new speed if we're currently moving
                if self.last_movement and not (
                    self.last_movement[1] is ThrustDirection.NONE
                    and self.last_movement[2] is TurnDirection.NONE
                ):
                    self._process_joystick_to_movement()
            else:
                logger.info("Already at the highest speed mode")
                self.controller.speed_out_of_bound(*SPEED_MODE_COLORS[self.current_speed_mode])

            logger.info(f"R1 pressed. Speed mode after: {self.current_speed_mode}")

        # Other buttons are not used for movement

    def _handle_joystick_event(self, joystick_name, x_value, y_value):
        """
        Handle raw joystick events from the controller.

        Args:
            joystick_name (str): Name of the joystick ("left" or "right")
            x_value (float): X-axis value (-1.0 to 1.0)
            y_value (float): Y-axis value (-1.0 to 1.0)
        """
        if joystick_name == JoystickType.LEFT.value:
            self.joystick_left_x = x_value
            self.joystick_left_y = y_value

            # Process left joystick for movement
            self._process_joystick_to_movement()

        elif joystick_name == JoystickType.RIGHT.value:
            self.joystick_right_x = x_value
            self.joystick_right_y = y_value

            # Process right joystick for camera movement
            if self.on_action_command and (abs(x_value) > DEAD_ZONE or abs(y_value) > DEAD_ZONE):
                self.on_action_command("camera", f"{x_value:.2f};{y_value:.2f}")

    def _handle_trigger_event(self, trigger_name, value):
        """
        Handle raw trigger events from the controller.

        Args:
            trigger_name (str): Name of the trigger ("L2" or "R2")
            value (float): Trigger value (0.0 to 1.0)
        """
        if trigger_name == TriggerType.R2.value and value > 0.5:
            # R2 for shooting or other action
            if self.on_action_command:
                self.on_action_command("shoot", f"{value * 100:.0f}")

    def _handle_dpad_event(self, direction, pressed):
        """
        Handle D-pad events from the controller.

        Args:
            direction (str): D-pad direction ("up", "down", "left", "right")
            pressed (bool): Whether the direction is pressed
        """
        if pressed:
            # Handle button press events
            if direction == DPadDirection.UP.value:
                self._send_movement_command(
                    self.speed_values[self.current_speed_mode],
                    ThrustDirection.FORWARD,
                    TurnDirection.NONE,
                    SHARP_TURN_FACTOR,
                )
            elif direction == DPadDirection.DOWN.value:
                self._send_movement_command(
                    self.speed_values[self.current_speed_mode],
                    ThrustDirection.BACKWARD,
                    TurnDirection.NONE,
                    SHARP_TURN_FACTOR,
                )
            elif direction == DPadDirection.LEFT.value:
                self._send_movement_command(
                    self.speed_values[self.current_speed_mode],
                    ThrustDirection.NONE,
                    TurnDirection.LEFT,
                    SHARP_TURN_FACTOR,
                )
            elif direction == DPadDirection.RIGHT.value:
                self._send_movement_command(
                    self.speed_values[self.current_speed_mode],
                    ThrustDirection.NONE,
                    TurnDirection.RIGHT,
                    SHARP_TURN_FACTOR,
                )
        else:
            # Handle button release events
            dpad_state = self.controller.get_status()["dpad"]

            # If this specific direction was controlling movement, check if we need to stop
            if (
                direction == DPadDirection.UP.value
                and self.last_movement
                and self.last_movement[1] is ThrustDirection.FORWARD
            ):
                # If up is released and was controlling forward movement, stop if no other relevant button is pressed
                if not dpad_state["up"]:
                    self._send_movement_command(
                        0, ThrustDirection.NONE, TurnDirection.NONE, SHARP_TURN_FACTOR
                    )
                    self.controller.stop_rumble()

            elif (
                direction == DPadDirection.DOWN.value
                and self.last_movement
                and self.last_movement[1] is ThrustDirection.BACKWARD
            ):
                # If down is released and was controlling backward movement, stop if no other relevant button is pressed
                if not dpad_state["down"]:
                    self._send_movement_command(
                        0, ThrustDirection.NONE, TurnDirection.NONE, SHARP_TURN_FACTOR
                    )
                    self.controller.stop_rumble()

            elif (
                direction == DPadDirection.LEFT.value
                and self.last_movement
                and self.last_movement[2] is TurnDirection.LEFT
            ):
                # If left is released and was controlling turning, stop if no other relevant button is pressed
                if not dpad_state["left"]:
                    self._send_movement_command(
                        0, ThrustDirection.NONE, TurnDirection.NONE, SHARP_TURN_FACTOR
                    )
                    self.controller.stop_rumble()

            elif (
                direction == DPadDirection.RIGHT.value
                and self.last_movement
                and self.last_movement[2] is TurnDirection.RIGHT
            ):
                # If right is released and was controlling turning, stop if no other relevant button is pressed
                if not dpad_state["right"]:
                    self._send_movement_command(
                        0, ThrustDirection.NONE, TurnDirection.NONE, SHARP_TURN_FACTOR
                    )
                    self.controller.stop_rumble()

    def _process_joystick_to_movement(self):
        """
        Process left joystick position into RaspTank movement commands using polar coordinates
        for more intuitive control across the entire joystick range.
        """
        x = self.joystick_left_x  # -1 to 1 (negative = left, positive = right)
        y = self.joystick_left_y  # -1 to 1 (negative = backward, positive = forward)

        # Calculate magnitude (distance from center)
        magnitude = math.sqrt(x * x + y * y)

        # Apply dead zone based on magnitude
        if magnitude < DEAD_ZONE:
            x, y = 0.0, 0.0
            magnitude = 0.0

        # Determine direction based on joystick angle if we're outside the dead zone
        if magnitude > 0:
            # Calculate angle in degrees (0° is forward, 90° is right, etc.)
            angle = math.degrees(math.atan2(x, y))  # atan2 gives better quadrant handling

            # Define directional zones as angles
            # Forward: -45° to 45°
            # Right: 45° to 135°
            # Backward: 135° to 225° (or -135° to -225°)
            # Left: 225° to 315° (or -135° to -45°)

            # Determine thrust direction based on angle
            if -45 <= angle <= 45:
                thrust_direction = ThrustDirection.FORWARD
                turn_direction = TurnDirection.NONE
            elif 135 <= angle <= 225 or -225 <= angle <= -135:
                thrust_direction = ThrustDirection.BACKWARD
                turn_direction = TurnDirection.NONE
            else:
                thrust_direction = ThrustDirection.NONE

                # Determine turn direction
                if 45 < angle < 135:
                    turn_direction = TurnDirection.RIGHT
                else:  # 225° to 315° or -135° to -45°
                    turn_direction = TurnDirection.LEFT

            # For diagonal movement, combine thrust and turn
            if abs(abs(angle) - 45) < 30:  # Forward-right or forward-left
                thrust_direction = ThrustDirection.FORWARD
                turn_direction = TurnDirection.RIGHT if angle > 0 else TurnDirection.LEFT
            elif abs(abs(angle) - 135) < 30:  # Backward-right or backward-left
                thrust_direction = ThrustDirection.BACKWARD
                turn_direction = TurnDirection.RIGHT if angle > 0 else TurnDirection.LEFT
        else:
            # No input (inside dead zone)
            thrust_direction = ThrustDirection.NONE
            turn_direction = TurnDirection.NONE

        # Get speed from current speed mode
        speed = self.speed_values[self.current_speed_mode]

        # Calculate turn factor based on magnitude for more precise control
        if turn_direction is not TurnDirection.NONE:
            # Map the magnitude to turn factor, preserving the sharp vs moderate logic
            if magnitude > TURN_THRESHOLD:
                turn_factor = SHARP_TURN_FACTOR
            else:
                # Scale turn factor based on magnitude
                normalized_magnitude = (magnitude - DEAD_ZONE) / (TURN_THRESHOLD - DEAD_ZONE)
                turn_factor = MODERATE_TURN_FACTOR * normalized_magnitude + 0.3 * (
                    1 - normalized_magnitude
                )
        else:
            turn_factor = SHARP_TURN_FACTOR  # No turning

        # Only send movement command if there's an actual direction
        if thrust_direction is not ThrustDirection.NONE or turn_direction is not TurnDirection.NONE:
            self._send_movement_command(speed, thrust_direction, turn_direction, turn_factor)
        else:
            # Stop movement if no direction
            self._send_movement_command(
                0, ThrustDirection.NONE, TurnDirection.NONE, SHARP_TURN_FACTOR
            )
            self.controller.stop_rumble()

    def _send_movement_command(
        self,
        speed: float,
        thrust_direction: ThrustDirection,
        turn_direction: TurnDirection,
        turn_factor: float,
    ):
        """
        Send a movement command to the RaspTank.

        Args:
            speed (float): Speed factor between 0.0 and 100.0
            thrust_direction (ThrustDirection): Thrust direction
            turn_direction (TurnDirection): Turn direction
            turn_factor (float): Turning factor between 0.0 and 1.0 (affects the sharpness of the turn)
        """
        # Clamp values to valid ranges
        speed = max(0.0, min(Speed.HIGH.value, speed))

        # Store current movement
        self.last_movement = (speed, thrust_direction, turn_direction, turn_factor)

        # Notify external systems via callback
        if self.on_movement_command:
            self.on_movement_command(speed, thrust_direction, turn_direction, turn_factor)
            logger.debug(
                f"Movement: speed={speed:.1f}, thrust={thrust_direction.value}, "
                f"turn={turn_direction.value}, factor={turn_factor:.2f}"
            )

            if speed == 0 or (
                thrust_direction == ThrustDirection.NONE and turn_direction == TurnDirection.NONE
            ):
                self.controller.stop_rumble()
            else:
                self.controller.on_movement(speed)

    def update_for_battery(self, battery_level):
        """
        Update LED based on battery level.

        Args:
            battery_level (int): Battery percentage (0-100)

        Returns:
            bool: True if battery warning is active
        """
        if self.has_feedback:
            # Returns True if battery warning is active, False otherwise
            return self.controller.update_feedback_for_battery(battery_level)
        return False

    def stop(self):
        """Stop all movement immediately."""
        self._send_movement_command(0, ThrustDirection.NONE, TurnDirection.NONE, SHARP_TURN_FACTOR)

        # Stop any active rumble
        if self.has_feedback:
            self.controller.stop_rumble()

        logger.info("Movement stopped")

    def get_status(self) -> Dict[str, Any]:
        """
        Get the current adapter status.

        Returns:
            Dict: Status information
        """
        return {
            "controller_connected": self.controller.get_status()["connected"],
            "last_movement": self.last_movement,
            "joystick_position": (self.joystick_left_x, self.joystick_left_y),
            "speed_mode": self.current_speed_mode,
            "current_speed": self.speed_values[self.current_speed_mode],
            "has_feedback": self.has_feedback,
        }
