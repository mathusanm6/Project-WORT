"""
DualSense controller module using pygame.
This module handles reading DualSense controller inputs and reporting raw inputs
via callbacks.
"""

import logging
import sys
import time
from typing import Callable, Dict, Optional, Tuple

import pygame

from src.dashboard.game_controller.controller_base import BaseController
from src.dashboard.game_controller.dualsense_feedback import DualSenseFeedback
from src.dashboard.game_controller.dualsense_mapping import (
    AXIS_MAPPING,
    BUTTON_MAPPING,
    DPAD_BUTTON_MAPPING,
    DPAD_TYPE,
    IS_MACOS,
    get_axis_name,
    get_button_name,
)

# Configure logging
logger = logging.getLogger(__name__)

# Controller Settings
JOYSTICK_DEAD_ZONE = 0.15  # Pygame joystick values are -1.0 to 1.0


class DualSenseController(BaseController):
    """PlayStation 5 DualSense controller interface using pygame.
    This class reads raw inputs and reports them via callbacks.
    """

    def __init__(
        self,
        on_button_event: Optional[Callable] = None,
        on_joystick_event: Optional[Callable] = None,
        on_trigger_event: Optional[Callable] = None,
        on_dpad_event: Optional[Callable] = None,
        enable_feedback: bool = True,
    ):
        """Initialize the DualSense controller using pygame.

        Args:
            on_button_event: Callback for button events
                Function signature: callback(button_name, pressed)
            on_joystick_event: Callback for joystick events
                Function signature: callback(joystick_name, x_value, y_value)
            on_trigger_event: Callback for trigger events
                Function signature: callback(trigger_name, value)
            on_dpad_event: Callback for D-pad events
                Function signature: callback(direction, pressed)
            enable_feedback: Whether to enable LED and rumble feedback
        """
        super().__init__()

        # Initialize callbacks
        self.on_button_event = on_button_event
        self.on_joystick_event = on_joystick_event
        self.on_trigger_event = on_trigger_event
        self.on_dpad_event = on_dpad_event

        # Extend controller state with DualSense-specific data
        self.controller_state.update(
            {
                "buttons": {},  # Button states (True/False)
                "joysticks": {},  # Joystick positions (x, y)
                "triggers": {},  # Trigger values (0.0-1.0)
                "dpad": {"up": False, "down": False, "left": False, "right": False},
            }
        )

        # Initialize feedback capabilities
        self.enable_feedback = enable_feedback
        self.feedback = None
        self.has_feedback = False

        if enable_feedback:
            try:
                self.feedback = DualSenseFeedback()
                self.has_feedback = self.feedback.initialized
                if self.has_feedback:
                    logger.info("DualSense LED and rumble feedback enabled")
                else:
                    logger.warning("DualSense feedback initialization failed")
            except Exception as e:
                logger.error(f"Error initializing DualSense feedback: {e}")
                self.has_feedback = False

    def _init_controller_states(self):
        """Initialize button and axis states for DualSense controller."""
        # Call parent implementation first
        super()._init_controller_states()

        # Initialize controller state with known buttons
        self.controller_state["buttons"] = {
            "cross": False,
            "circle": False,
            "square": False,
            "triangle": False,
            "L1": False,
            "R1": False,
            "L2": False,
            "R2": False,
            "share": False,
            "options": False,
            "PS": False,
            "L3": False,
            "R3": False,
            "touchpad": False,
        }

        self.controller_state["joysticks"] = {"left": (0.0, 0.0), "right": (0.0, 0.0)}

        self.controller_state["triggers"] = {"L2": 0.0, "R2": 0.0}

        # Set default LED color if feedback is enabled
        if self.has_feedback:
            self.feedback.set_led_color(255, 255, 255)  # Default white

    def start(self):
        """Start listening for controller events.

        On macOS, pygame event handling must happen on the main thread.
        For macOS compatibility, don't use this method - instead call
        _process_events() directly from your main thread.
        """
        if IS_MACOS:
            logger.warning(
                "On macOS, pygame event handling must happen on the main thread. "
                "Call _process_events() manually from your main thread instead."
            )
            return super().start(use_threading=False)
        else:
            return super().start(use_threading=True)

    def _read_controller_state(self):
        """Read the current state of the DualSense controller."""
        try:
            if not self.joystick:
                return

            # Update previous button states
            for button in self.button_states:
                self.prev_button_states[button] = self.button_states[button]

            # Update previous axis states
            for axis in self.axis_states:
                self.prev_axis_states[axis] = self.axis_states[axis]

            # Update button states
            for i in range(self.joystick.get_numbuttons()):
                self.button_states[i] = self.joystick.get_button(i)

                # Check for button state changes and handle them
                if self.button_states[i] != self.prev_button_states.get(i, False):
                    self._handle_button(i, self.button_states[i])

            # Update axis states and handle joystick inputs
            for i in range(self.joystick.get_numaxes()):
                self.axis_states[i] = self.joystick.get_axis(i)

                # Check if there's a significant change in axis value
                if abs(self.axis_states[i] - self.prev_axis_states.get(i, 0.0)) > 0.05:
                    self._handle_axis(i, self.axis_states[i])

            # Try to read hat (D-pad) if available and we're using hat mode
            if DPAD_TYPE == "hat":
                try:
                    if self.joystick.get_numhats() > 0:
                        hat = self.joystick.get_hat(0)  # Usually D-pad is the first hat
                        self._handle_hat(hat)
                except:
                    pass  # Hat might not be available on this controller

        except Exception as e:
            logger.error(f"Error reading controller state: {e}")

    def _handle_button(self, button_id, pressed):
        """Handle raw button press/release events.

        Args:
            button_id (int): Button ID
            pressed (bool): Whether the button is pressed
        """
        button_name = get_button_name(button_id)

        if button_name:
            # Update internal state
            if button_name in self.controller_state["buttons"]:
                self.controller_state["buttons"][button_name] = pressed

                # Call button callback if provided
                if self.on_button_event:
                    self.on_button_event(button_name, pressed)

                logger.debug(f"Button event: {button_name} {'pressed' if pressed else 'released'}")

        # Check if this is a D-pad button if we're using button mode for D-pad
        elif DPAD_TYPE == "buttons":
            for direction, dir_button_id in DPAD_BUTTON_MAPPING.items():
                if button_id == dir_button_id:
                    self.controller_state["dpad"][direction] = pressed

                    # Call dpad callback if provided
                    if self.on_dpad_event:
                        self.on_dpad_event(direction, pressed)

                    logger.debug(f"D-pad event: {direction} {'pressed' if pressed else 'released'}")
                    break

    def _handle_axis(self, axis_id, value):
        """Handle raw axis value changes.

        Args:
            axis_id (int): Axis ID
            value (float): Axis value (-1.0 to 1.0)
        """
        axis_name = get_axis_name(axis_id)

        if axis_name:
            # Handle joystick axes
            if axis_name == "left_x" or axis_name == "left_y":
                left_x = self.axis_states.get(AXIS_MAPPING["left_x"], 0.0)
                left_y = -self.axis_states.get(
                    AXIS_MAPPING["left_y"], 0.0
                )  # Invert Y so up is positive

                # Apply dead zone
                if abs(left_x) < JOYSTICK_DEAD_ZONE:
                    left_x = 0.0
                if abs(left_y) < JOYSTICK_DEAD_ZONE:
                    left_y = 0.0

                # Update state
                self.controller_state["joysticks"]["left"] = (left_x, left_y)

                # Call joystick callback if provided
                if self.on_joystick_event:
                    self.on_joystick_event("left", left_x, left_y)

            elif axis_name == "right_x" or axis_name == "right_y":
                right_x = self.axis_states.get(AXIS_MAPPING["right_x"], 0.0)
                right_y = -self.axis_states.get(AXIS_MAPPING["right_y"], 0.0)  # Invert Y

                # Apply dead zone
                if abs(right_x) < JOYSTICK_DEAD_ZONE:
                    right_x = 0.0
                if abs(right_y) < JOYSTICK_DEAD_ZONE:
                    right_y = 0.0

                # Update state
                self.controller_state["joysticks"]["right"] = (right_x, right_y)

                # Call joystick callback if provided
                if self.on_joystick_event:
                    self.on_joystick_event("right", right_x, right_y)

            # Handle triggers (normalize from -1.0...1.0 to 0.0...1.0)
            elif axis_name == "L2":
                L2_value = (value + 1) / 2
                self.controller_state["triggers"]["L2"] = L2_value

                if self.on_trigger_event:
                    self.on_trigger_event("L2", L2_value)

            elif axis_name == "R2":
                R2_value = (value + 1) / 2
                self.controller_state["triggers"]["R2"] = R2_value

                if self.on_trigger_event:
                    self.on_trigger_event("R2", R2_value)

    def _handle_hat(self, hat_value):
        """Handle hat (D-pad) input.

        Args:
            hat_value (tuple): (x, y) values for the hat, typically (-1, 0, 1) for each axis
        """
        x, y = hat_value

        # Update D-pad state
        prev_dpad = self.controller_state["dpad"].copy()

        # Reset all directions first
        self.controller_state["dpad"]["up"] = False
        self.controller_state["dpad"]["down"] = False
        self.controller_state["dpad"]["left"] = False
        self.controller_state["dpad"]["right"] = False

        # Set active directions
        if y == 1:  # Up
            self.controller_state["dpad"]["up"] = True
        elif y == -1:  # Down
            self.controller_state["dpad"]["down"] = True

        if x == -1:  # Left
            self.controller_state["dpad"]["left"] = True
        elif x == 1:  # Right
            self.controller_state["dpad"]["right"] = True

        # Trigger callbacks for changes
        if self.on_dpad_event:
            for direction in ["up", "down", "left", "right"]:
                if self.controller_state["dpad"][direction] != prev_dpad[direction]:
                    self.on_dpad_event(direction, self.controller_state["dpad"][direction])

    def get_status(self) -> Dict:
        """Get the current controller status.

        Returns:
            Dict: Controller status information
        """
        return {
            "connected": self.controller_state["is_connected"],
            "buttons": self.controller_state["buttons"].copy(),
            "joysticks": self.controller_state["joysticks"].copy(),
            "triggers": self.controller_state["triggers"].copy(),
            "dpad": self.controller_state["dpad"].copy(),
            "has_feedback": self.has_feedback,
        }

    def update_feedback_for_battery(self, battery_level: int) -> bool:
        """Update LED based on battery level.

        Args:
            battery_level (int): Battery percentage (0-100)

        Returns:
            bool: True if battery warning is active
        """
        if not self.has_feedback:
            return False

        return self.feedback.update_for_battery(battery_level)

    def set_led_color(self, r: int, g: int, b: int) -> bool:
        """Set the controller LED color.

        Args:
            r, g, b: Color values (0-255)

        Returns:
            bool: Success or failure
        """
        if not self.has_feedback:
            return False

        return self.feedback.set_led_color(r, g, b)

    def set_rumble(self, low_freq: int = 0, high_freq: int = 0, duration_ms: int = 0) -> bool:
        """Set rumble effect.

        Args:
            low_freq: Low frequency rumble intensity (0-65535)
            high_freq: High frequency rumble intensity (0-65535)
            duration_ms: Duration in milliseconds (0 = continuous until stopped)

        Returns:
            bool: Success or failure
        """
        if not self.has_feedback:
            return False

        return self.feedback.set_rumble(low_freq, high_freq, duration_ms)

    def stop_rumble(self) -> None:
        """Stop any active rumble effects."""
        if self.has_feedback:
            self.feedback.stop_rumble()

    def speed_out_of_bound(self, r: int, g: int, b: int) -> None:
        """

        Args:
            color: RGB color tuple (0-255)
        """
        if self.has_feedback:
            for _ in range(3):
                self.feedback.set_rumble(65535, 65535, 200)
                self.feedback.set_led_color(r, g, b)
                time.sleep(0.15)
                self.feedback.set_rumble(0, 0, 200)
                self.feedback.set_led_color(0, 0, 0)  # Off
                time.sleep(0.15)
            self.feedback.set_led_color(r, g, b)

    def cleanup(self):
        """Clean up resources."""
        logger.info("Cleaning up controller resources")

        # Stop rumble and clean up feedback resources
        if self.has_feedback and self.feedback:
            try:
                logger.info("Cleaning up DualSense feedback resources")
                self.feedback.stop_rumble()
                self.feedback.cleanup()
            except Exception as e:
                logger.error(f"Error cleaning up DualSense feedback: {e}")

        self.stop()

        # Close pygame joystick
        if self.joystick:
            try:
                logger.info("Closing controller")
                self.joystick.quit()
                self.controller_state["is_connected"] = False
            except Exception as e:
                logger.error(f"Error closing controller: {e}")
