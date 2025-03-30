"""
RaspTank Adapter for Controller Inputs - Updated for new feedback collection API

This adapter converts raw controller inputs into commands
compatible with the RaspTank hardware implementation.
"""

from typing import Any, Callable, Dict, Optional

# Import from src.common
from src.common.constants.actions import ActionType
from src.common.constants.controller import (
    JOYSTICK_DEAD_ZONE,
    JOYSTICK_HORIZONTAL_THRESHOLD,
    TRIGGER_THRESHOLD,
)
from src.common.enum.movement import (
    CurvedTurnRate,
    SpeedMode,
    ThrustDirection,
    TurnDirection,
    TurnType,
)
from src.common.logging.logger_api import Logger

# Import from the new modular controller structure
from src.dashboard.dualsense.controller import DualSenseController
from src.dashboard.dualsense.controller_events import (
    ButtonType,
    DPadDirection,
    JoystickType,
    TriggerType,
)


class ControllerAdapter:
    """
    Adapter that converts controller inputs into commands
    compatible with the RaspTank hardware implementation.
    """

    def __init__(
        self,
        controller_adapter_logger: Logger,
        controller: DualSenseController,
        on_movement_command: Optional[Callable] = None,
        on_action_command: Optional[Callable] = None,
    ):
        """Initialize the RaspTank movement adapter.

        Args:
            controller: The DualSense controller to adapt
            on_movement_command: Callback for movement commands
                Function signature: callback(speed, thrust_direction, turn_direction, turn_factor)
            on_action_command: Callback for action commands
                Function signature: callback(action_name)
        """
        self.logger = controller_adapter_logger
        self.logger.infow("Initializing RaspTank Controller Adapter")

        self.controller = controller
        self.on_movement_command = on_movement_command
        self.on_action_command = on_action_command

        # Check if controller has feedback capabilities
        self.has_feedback = hasattr(controller, "has_feedback") and controller.has_feedback
        if self.has_feedback:
            self.logger.infow("DualSense feedback features enabled for movement adapter")
        else:
            self.logger.infow("DualSense feedback features not available")

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

        # Track active D-pad directions for pivot mode updates
        self.active_dpad_directions = {
            DPadDirection.UP.value: False,
            DPadDirection.DOWN.value: False,
            DPadDirection.LEFT.value: False,
            DPadDirection.RIGHT.value: False,
        }

        # Track trigger values
        self.l2_trigger_value = 0.0
        self.r2_trigger_value = 0.0

        # Initialize turning state
        self.thrust_direction = ThrustDirection.NONE
        self.turn_direction = TurnDirection.NONE
        self.turn_type = TurnType.NONE
        self.curved_turn_rate = CurvedTurnRate.NONE

        # Speed control
        self.speed_modes = SpeedMode.get_speed_modes()  # Get all speed modes except STOP
        self.speed_values = (
            SpeedMode.get_speed_values()
        )  # Get the speed values for all speed modes except STOP
        self.current_speed_mode_idx = len(self.speed_values) // 2  # Start in the middle speed mode

        # Last movement command sent
        self.last_movement = None

        # Pivot mode
        self.pivot_mode = False

        # Set initial LED color based on speed mode if feedback available
        if self.has_feedback:
            r, g, b = self.speed_modes[self.current_speed_mode_idx].color
            self.controller.feedback_collection.set_led_color(r, g, b)

        self.logger.infow("RaspTank Controller Adapter initialized with DualSense controller")
        self.logger.infow(
            "Initial speed mode",
            "mode_idx",
            self.current_speed_mode_idx,
            "label",
            "LOW",
            "value",
            self.speed_values[self.current_speed_mode_idx],
        )

    def _handle_button_event(self, button_name, pressed):
        """
        Handle raw button events from the controller.

        Args:
            button_name (str): Name of the button
            pressed (bool): Whether the button is pressed
        """
        # Log raw button event for debugging
        self.logger.debugw("Button event", "button", button_name, "pressed", pressed)

        # Handle speed control with L1 button (decrease speed)
        if button_name == ButtonType.L1.value and pressed:
            # Log current speed mode for debugging
            self.logger.debugw(
                "L1 pressed", "current_speed_mode_before", self.current_speed_mode_idx
            )

            # Decrease speed mode (without wrap-around)
            if self.current_speed_mode_idx > 0:
                self.current_speed_mode_idx -= 1
                self.logger.debugw(
                    "Speed decreased",
                    "mode",
                    self.current_speed_mode_idx,
                    "value",
                    self.speed_values[self.current_speed_mode_idx],
                )

                # Update LED color based on new speed mode and rumble
                if self.has_feedback:
                    r, g, b = self.speed_modes[self.current_speed_mode_idx].color
                    self.controller.feedback_collection.on_speed_change(r, g, b)

                # Update movement with new speed if we're currently moving
                if self.last_movement and not (
                    self.last_movement[0] is ThrustDirection.NONE
                    and self.last_movement[1] is TurnDirection.NONE
                ):
                    self._process_joystick_to_movement()

                    # Also update any active D-pad movements with the new speed
                    self._update_active_dpad_movements()
            else:
                self.logger.debugw("Already at the lowest speed mode")
                if self.has_feedback:
                    r, g, b = self.speed_modes[self.current_speed_mode_idx].color
                    self.controller.feedback_collection.on_speed_out_of_bound(r, g, b)

            self.logger.debugw("L1 pressed", "speed_mode_after", self.current_speed_mode_idx)

        # Handle speed control with R1 button (increase speed)
        elif button_name == ButtonType.R1.value and pressed:
            # Log current speed mode for debugging
            self.logger.debugw(
                "R1 pressed", "current_speed_mode_before", self.current_speed_mode_idx
            )

            # Increase speed mode (without wrap-around)
            if self.current_speed_mode_idx < len(self.speed_values) - 1:
                self.current_speed_mode_idx += 1
                self.logger.debugw(
                    "Speed increased",
                    "mode",
                    self.current_speed_mode_idx,
                    "value",
                    self.speed_values[self.current_speed_mode_idx],
                )

                # Update LED color based on new speed mode and rumble
                if self.has_feedback:
                    r, g, b = self.speed_modes[self.current_speed_mode_idx].color
                    self.controller.feedback_collection.on_speed_change(r, g, b)

                # Update movement with new speed if we're currently moving
                if self.last_movement and not (
                    self.last_movement[0] is ThrustDirection.NONE
                    and self.last_movement[1] is TurnDirection.NONE
                ):
                    self._process_joystick_to_movement()

                    # Also update any active D-pad movements with the new speed
                    self._update_active_dpad_movements()
            else:
                self.logger.debugw("Already at the highest speed mode")
                if self.has_feedback:
                    r, g, b = self.speed_modes[self.current_speed_mode_idx].color
                    self.controller.feedback_collection.on_speed_out_of_bound(r, g, b)

            self.logger.debugw("R1 pressed", "speed_mode_after", self.current_speed_mode_idx)

        # Shoot using the SQUARE button
        elif button_name == ButtonType.SQUARE.value and pressed:
            if self.on_action_command:
                self.logger.debugw("Shoot command sent")
                self.on_action_command(ActionType.SHOOT)
                if self.has_feedback:
                    # Updated: no longer pass LED color, feedback collection tracks it internally
                    self.controller.feedback_collection.on_shoot()

        # Toggle pivot mode using the TRIANGLE button
        elif button_name == ButtonType.TRIANGLE.value and pressed:
            self.pivot_mode = not self.pivot_mode
            self.logger.debugw("Pivot mode toggled", "pivot_mode", self.pivot_mode)
            if self.has_feedback:
                # Updated: no longer pass LED color, feedback collection tracks it internally
                self.controller.feedback_collection.on_pivot_mode()

    def _update_active_dpad_movements(self):
        """Update any active D-pad movements with the current pivot mode and speed."""
        dpad_state = self.controller.get_status()["dpad"]

        # First check each direction
        if dpad_state["up"] and self.active_dpad_directions[DPadDirection.UP.value]:
            self._send_movement_command(
                ThrustDirection.FORWARD,
                TurnDirection.NONE,
                TurnType.NONE,
                self.speed_modes[self.current_speed_mode_idx],
                CurvedTurnRate.NONE,
            )
        elif dpad_state["down"] and self.active_dpad_directions[DPadDirection.DOWN.value]:
            self._send_movement_command(
                ThrustDirection.BACKWARD,
                TurnDirection.NONE,
                TurnType.NONE,
                self.speed_modes[self.current_speed_mode_idx],
                CurvedTurnRate.NONE,
            )
        elif dpad_state["left"] and self.active_dpad_directions[DPadDirection.LEFT.value]:
            self._send_movement_command(
                ThrustDirection.NONE,
                TurnDirection.LEFT,
                TurnType.PIVOT if self.pivot_mode else TurnType.SPIN,
                self.speed_modes[self.current_speed_mode_idx],
                CurvedTurnRate.NONE,
            )
        elif dpad_state["right"] and self.active_dpad_directions[DPadDirection.RIGHT.value]:
            self._send_movement_command(
                ThrustDirection.NONE,
                TurnDirection.RIGHT,
                TurnType.PIVOT if self.pivot_mode else TurnType.SPIN,
                self.speed_modes[self.current_speed_mode_idx],
                CurvedTurnRate.NONE,
            )

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
            # if self.on_action_command and (
            #     abs(x_value) > JOYSTICK_DEAD_ZONE or abs(y_value) > JOYSTICK_DEAD_ZONE
            # ):
            #     self.on_action_command("camera", f"{x_value:.2f};{y_value:.2f}")

    def _handle_trigger_event(self, trigger_name, value):
        """
        Handle raw trigger events from the controller.

        Args:
            trigger_name (str): Name of the trigger ("L2" or "R2")
            value (float): Trigger value (0.0 to 1.0)
        """
        if trigger_name == TriggerType.R2.value:
            # R2 for forward movement
            self.r2_trigger_value = value if value > TRIGGER_THRESHOLD else 0.0
            self.logger.debugw(
                "R2 trigger pressed", "value", value, "current_value", self.r2_trigger_value
            )
        elif trigger_name == TriggerType.L2.value:
            # L2 for backward movement
            self.l2_trigger_value = value if value > TRIGGER_THRESHOLD else 0.0
            self.logger.debugw(
                "L2 trigger pressed", "value", value, "current_value", self.l2_trigger_value
            )

        # Process combined movement from triggers and joystick
        self._process_combined_inputs()

    def _handle_dpad_event(self, direction, pressed):
        """
        Handle D-pad events from the controller.

        Args:
            direction (str): D-pad direction ("up", "down", "left", "right")
            pressed (bool): Whether the direction is pressed
        """
        # Update the active direction tracking
        self.active_dpad_directions[direction] = pressed

        if pressed:
            # Handle button press events
            if direction == DPadDirection.UP.value:
                self._send_movement_command(
                    ThrustDirection.FORWARD,
                    TurnDirection.NONE,
                    TurnType.NONE,
                    self.speed_modes[self.current_speed_mode_idx],
                    CurvedTurnRate.NONE,
                )
            elif direction == DPadDirection.DOWN.value:
                self._send_movement_command(
                    ThrustDirection.BACKWARD,
                    TurnDirection.NONE,
                    TurnType.NONE,
                    self.speed_modes[self.current_speed_mode_idx],
                    CurvedTurnRate.NONE,
                )
            elif direction == DPadDirection.LEFT.value:
                self._send_movement_command(
                    ThrustDirection.NONE,
                    TurnDirection.LEFT,
                    TurnType.PIVOT if self.pivot_mode else TurnType.SPIN,
                    self.speed_modes[self.current_speed_mode_idx],
                    CurvedTurnRate.NONE,
                )
            elif direction == DPadDirection.RIGHT.value:
                self._send_movement_command(
                    ThrustDirection.NONE,
                    TurnDirection.RIGHT,
                    TurnType.PIVOT if self.pivot_mode else TurnType.SPIN,
                    self.speed_modes[self.current_speed_mode_idx],
                    CurvedTurnRate.NONE,
                )
        else:
            # Handle button release events
            dpad_state = self.controller.get_status()["dpad"]

            # If this specific direction was controlling movement, check if we need to stop
            if (
                direction == DPadDirection.UP.value
                and self.last_movement
                and self.last_movement[0] is ThrustDirection.FORWARD
            ):
                # If up is released and was controlling forward movement, stop if no other relevant button is pressed
                if not dpad_state["up"]:
                    self._send_movement_command(
                        ThrustDirection.NONE,
                        TurnDirection.NONE,
                        TurnType.NONE,
                        SpeedMode.STOP,
                        CurvedTurnRate.NONE,
                    )

            elif (
                direction == DPadDirection.DOWN.value
                and self.last_movement
                and self.last_movement[0] is ThrustDirection.BACKWARD
            ):
                # If down is released and was controlling backward movement, stop if no other relevant button is pressed
                if not dpad_state["down"]:
                    self._send_movement_command(
                        ThrustDirection.NONE,
                        TurnDirection.NONE,
                        TurnType.NONE,
                        SpeedMode.STOP,
                        CurvedTurnRate.NONE,
                    )

            elif (
                direction == DPadDirection.LEFT.value
                and self.last_movement
                and self.last_movement[1] is TurnDirection.LEFT
            ):
                # If left is released and was controlling turning, stop if no other relevant button is pressed
                if not dpad_state["left"]:
                    self._send_movement_command(
                        ThrustDirection.NONE,
                        TurnDirection.NONE,
                        TurnType.NONE,
                        SpeedMode.STOP,
                        CurvedTurnRate.NONE,
                    )

            elif (
                direction == DPadDirection.RIGHT.value
                and self.last_movement
                and self.last_movement[1] is TurnDirection.RIGHT
            ):
                # If right is released and was controlling turning, stop if no other relevant button is pressed
                if not dpad_state["right"]:
                    self._send_movement_command(
                        ThrustDirection.NONE,
                        TurnDirection.NONE,
                        TurnType.NONE,
                        SpeedMode.STOP,
                        CurvedTurnRate.NONE,
                    )

    def _process_joystick_to_movement(self):
        """
        Process left joystick position into RaspTank movement commands using polar coordinates
        for more intuitive control across the entire joystick range.
        """
        x = self.joystick_left_x  # -1 to 1 (negative = left, positive = right)

        # Apply dead zone
        if abs(x) < JOYSTICK_DEAD_ZONE:
            self.turn_direction = TurnDirection.NONE
            self.turn_type = TurnType.NONE
            self.curved_turn_rate = CurvedTurnRate.NONE
        else:
            # Determine turn direction from joystick X axis
            if x > JOYSTICK_HORIZONTAL_THRESHOLD:
                self.turn_direction = TurnDirection.RIGHT
            elif x < -JOYSTICK_HORIZONTAL_THRESHOLD:
                self.turn_direction = TurnDirection.LEFT
            else:
                self.turn_direction = TurnDirection.NONE

            # If turning, set turn type and calculate curved turn rate
            if self.turn_direction is not TurnDirection.NONE:
                # Calculate curved turn rate based on how far the stick is pushed
                turn_magnitude = abs(x)

                # Map magnitude to the nearest valid CurvedTurnRate value
                valid_rates = CurvedTurnRate.get_curved_turn_rate_values()
                closest_rate = min(valid_rates, key=lambda rate: abs(rate - turn_magnitude))
                self.curved_turn_rate = CurvedTurnRate(closest_rate)
                self.turn_type = TurnType.CURVE
            else:
                self.turn_type = TurnType.NONE
                self.curved_turn_rate = CurvedTurnRate.NONE

        # Process combined inputs to determine final movement
        self._process_combined_inputs()

    def _process_combined_inputs(self):
        """
        Combines trigger inputs (for thrust) with joystick inputs (for turning)
        to create the final movement command.
        """
        # Determine thrust direction based on triggers
        # If both triggers are pressed, priority goes to R2 (forward)
        if hasattr(self, "r2_trigger_value") and self.r2_trigger_value > 0.4:
            self.thrust_direction = ThrustDirection.FORWARD
            # Scale speed by trigger value
            speed_idx = min(
                len(self.speed_modes) - 1, int(self.r2_trigger_value * len(self.speed_modes))
            )
            speed_mode = self.speed_modes[speed_idx]
        elif hasattr(self, "l2_trigger_value") and self.l2_trigger_value > 0.4:
            self.thrust_direction = ThrustDirection.BACKWARD
            # Scale speed by trigger value
            speed_idx = min(
                len(self.speed_modes) - 1, int(self.l2_trigger_value * len(self.speed_modes))
            )
            speed_mode = self.speed_modes[speed_idx]
        else:
            # Reset thrust direction and speed when both triggers are below threshold
            self.thrust_direction = ThrustDirection.NONE
            speed_mode = SpeedMode.STOP

        # If we're not thrusting but we are turning, use the current turn mode (pivot or spin)
        if (
            self.thrust_direction is ThrustDirection.NONE
            and self.turn_direction is not TurnDirection.NONE
        ):
            self.turn_type = TurnType.PIVOT if self.pivot_mode else TurnType.SPIN
            speed_mode = self.speed_modes[self.current_speed_mode_idx]

            self._send_movement_command(
                self.thrust_direction,
                self.turn_direction,
                self.turn_type,
                speed_mode,
                self.curved_turn_rate,
            )

        if (
            self.thrust_direction is not ThrustDirection.NONE
            and self.turn_direction is not TurnDirection.NONE
        ):
            self.turn_type = TurnType.CURVE
            self._send_movement_command(
                self.thrust_direction,
                self.turn_direction,
                self.turn_type,
                speed_mode,
                self.curved_turn_rate,
            )

        # Only send command if there's actual movement
        if (
            self.thrust_direction is ThrustDirection.NONE
            and self.turn_direction is TurnDirection.NONE
        ):
            # Stop if no input and we were moving before
            if self.last_movement and not (
                self.last_movement[0] is ThrustDirection.NONE
                and self.last_movement[1] is TurnDirection.NONE
            ):
                self._send_movement_command(
                    ThrustDirection.NONE,
                    TurnDirection.NONE,
                    TurnType.NONE,
                    SpeedMode.STOP,
                    CurvedTurnRate.NONE,
                )

    def _send_movement_command(
        self,
        thrust_direction: ThrustDirection,
        turn_direction: TurnDirection,
        turn_type: TurnType,
        speed_mode: SpeedMode,
        curved_turn_rate: CurvedTurnRate,
    ):
        """
        Send a movement command to the RaspTank.

        Args:
            thrust_direction (ThrustDirection): Thrust direction
            turn_direction (TurnDirection): Turn direction
            turn_type (TurnType): Turn type
            speed (Speed): Speed factor
            curved_turn_rate (CurvedTurnRate): Rate of turn for CURVE turn type (0.0 to 1.0 with 0.0 being no curve)
        """
        # Store current movement
        self.last_movement = (
            thrust_direction,
            turn_direction,
            turn_type,
            speed_mode,
            curved_turn_rate,
        )

        # Notify external systems via callback
        if self.on_movement_command:
            self.on_movement_command(
                thrust_direction, turn_direction, turn_type, speed_mode, curved_turn_rate
            )
            self.logger.debugw(
                "Movement command sent",
                "thrust_direction",
                thrust_direction,
                "turn_direction",
                turn_direction,
                "turn_type",
                turn_type,
                "speed_mode",
                speed_mode,
                "curved_turn_rate",
                curved_turn_rate,
            )

            if self.has_feedback:
                self.controller.feedback_collection.on_move(
                    thrust_direction, turn_direction, turn_type, speed_mode, curved_turn_rate
                )

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
            return self.controller.feedback_collection.update_for_battery(battery_level)
        return False

    def stop(self):
        """Stop all movement immediately."""
        self._send_movement_command(
            ThrustDirection.NONE,
            TurnDirection.NONE,
            TurnType.NONE,
            SpeedMode.STOP,
            CurvedTurnRate.NONE,
        )

        # Make sure rumble is stopped
        if self.has_feedback:
            self.controller.feedback_collection.stop_rumble()

        self.logger.infow("Movement stopped")

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
            "current_speed_mode_idx": self.current_speed_mode_idx,
            "current_speed_mode": self.speed_modes[self.current_speed_mode_idx],
            "current_speed_value": self.speed_values[self.current_speed_mode_idx],
            "has_feedback": self.has_feedback,
            "pivot_mode": self.pivot_mode,
            "active_dpad_directions": self.active_dpad_directions,
        }
