"""This module holds a collection of feedback mechanisms for the Dualsense controller."""

import math
import random
import threading
import time

# Import from src.common
from src.common.constants.controller import BATTERY_CRITICAL_LEVEL, BATTERY_WARNING_LEVEL
from src.common.enum.movement import (
    CurvedTurnRate,
    SpeedMode,
    ThrustDirection,
    TurnDirection,
    TurnType,
)

# Import from src.dashboard
from src.dashboard.game_controller.dualsense_feedback import DualSenseFeedback


class DualsenseFeedbackCollection:
    def __init__(self, feedback: DualSenseFeedback):
        self.feedback = feedback

    def on_speed_out_of_bound(self, r: int, g: int, b: int) -> None:
        """

        Args:
            color: RGB color tuple (0-255)
        """
        for _ in range(3):
            self.feedback.set_rumble(65535, 65535, 200)
            self.feedback.set_led_color(r, g, b)
            time.sleep(0.15)
            self.feedback.set_rumble(0, 0, 200)
            self.feedback.set_led_color(0, 0, 0)  # Off
            time.sleep(0.15)
        self.feedback.set_led_color(r, g, b)

    def on_speed_change(self, r: int, g: int, b: int) -> None:
        """

        Args:
            color: RGB color tuple (0-255)
        """
        self.feedback.set_led_color(r, g, b)
        self.feedback.set_rumble(1500, 1500, 200)

    def on_move(
        self,
        thrust_direction: ThrustDirection,
        turn_direction: TurnDirection,
        turn_type: TurnType,
        speed: SpeedMode,
        curved_turn_rate: CurvedTurnRate,
    ) -> None:
        """Create realistic vehicle movement rumble feedback based on speed.

        Args:
            thrust_direction (ThrustDirection): Thrust direction
            turn_direction (TurnDirection): Turn direction
            turn_type (TurnType): Turn type
            speed (Speed): Speed factor between 0.0 and 100.0
            curved_turn_rate (CurvedTurnRate): Rate of turn for CURVE turn type (0.0 to 1.0)
        """
        if thrust_direction == ThrustDirection.NONE and turn_direction == TurnDirection.NONE:
            if speed == SpeedMode.STOP:
                self.stop_rumble()
            else:
                raise ValueError("Invalid movement: speed without thrust or turn")
            return

        # Stop any existing rumble thread before starting a new one
        if hasattr(self, "_rumble_active") and self._rumble_active:
            self._rumble_active = False
            if hasattr(self, "_rumble_thread") and self._rumble_thread.is_alive():
                self._rumble_thread.join(timeout=0.5)

        # Start a new thread for continuous rumble
        self._rumble_active = True
        self._rumble_thread = threading.Thread(
            target=self._continuous_rumble,
            args=(thrust_direction, turn_direction, turn_type, speed, curved_turn_rate),
        )
        self._rumble_thread.daemon = True
        self._rumble_thread.start()

    def stop_rumble(self):
        """Stop the rumble effect."""
        if hasattr(self, "_rumble_active"):
            self._rumble_active = False

        # Immediately stop the rumble effect
        self.feedback.set_rumble(0, 0, 0)

    def _continuous_rumble(
        self,
        thrust_direction: ThrustDirection,
        turn_direction: TurnDirection,
        turn_type: TurnType,
        speed: SpeedMode,
        curved_turn_rate: CurvedTurnRate,
    ):
        """Create a continuous rumble pattern that simulates realistic tank movement.

        Focuses on:
        - Distinct feedback for both sides of the controller
        - Clear differentiation between straight movement and turns
        - Unique feedback for different turn types (Curve, Spin, Pivot)
        - Noticeable speed differences between gears
        """
        try:
            # Base configuration based on speed
            if speed == SpeedMode.STOP:
                base_intensity = 0
                variation = 0
                cycle_time = 1
            elif speed == SpeedMode.GEAR_1:  # 70%
                base_intensity = 15000
                variation = 7000
                cycle_time = 0.9
            elif speed == SpeedMode.GEAR_2:  # 80%
                base_intensity = 22000
                variation = 9000
                cycle_time = 0.75
            elif speed == SpeedMode.GEAR_3:  # 90%
                base_intensity = 30000
                variation = 12000
                cycle_time = 0.6
            elif speed == SpeedMode.GEAR_4:  # 100%
                base_intensity = 40000
                variation = 15000
                cycle_time = 0.45
            else:
                raise ValueError("Invalid speed mode")

            # Default pattern (straight movement)
            left_intensity_modifier = 1.0
            right_intensity_modifier = 1.0
            pattern_style = "continuous"  # Default pattern

            # VERY distinct patterns for different turn types
            if turn_direction != TurnDirection.NONE:
                if turn_type == TurnType.CURVE:
                    # For curve turns - one track moves faster than the other
                    # The difference increases with curved_turn_rate
                    pattern_style = "differential"
                    curve_strength = curved_turn_rate.value if curved_turn_rate else 0.5

                    if turn_direction == TurnDirection.LEFT:
                        # Left turn - right track moves faster
                        left_intensity_modifier = max(0.4, 1.0 - curve_strength * 0.6)
                        right_intensity_modifier = min(1.6, 1.0 + curve_strength * 0.6)
                    else:  # RIGHT
                        # Right turn - left track moves faster
                        left_intensity_modifier = min(1.6, 1.0 + curve_strength * 0.6)
                        right_intensity_modifier = max(0.4, 1.0 - curve_strength * 0.6)

                elif turn_type == TurnType.SPIN:
                    # For spin turns - one track forward, one backward
                    # Very distinctive "alternating" pattern
                    pattern_style = "alternating"
                    # These modifiers will be used differently in the alternating pattern
                    left_intensity_modifier = 1.2
                    right_intensity_modifier = 1.2

                elif turn_type == TurnType.PIVOT:
                    # For pivot turns - one track stationary, one moves
                    pattern_style = "pivot"
                    if turn_direction == TurnDirection.LEFT:
                        # Left pivot - right track moves, left stationary
                        left_intensity_modifier = 0.2
                        right_intensity_modifier = 1.5
                    else:  # RIGHT
                        # Right pivot - left track moves, right stationary
                        left_intensity_modifier = 1.5
                        right_intensity_modifier = 0.2

            # Run the rumble pattern until stopped
            start_time = time.time()

            while self._rumble_active:
                elapsed = time.time() - start_time

                # Apply different patterns based on movement type
                if pattern_style == "continuous":
                    # Standard continuous pattern for straight movement
                    # Slight phase difference between L/R for tank track feel
                    left_wave = math.sin(elapsed * (2 * math.pi / cycle_time))
                    right_wave = math.sin(elapsed * (2 * math.pi / cycle_time) + 0.5)

                    left_intensity = int(base_intensity + left_wave * variation)
                    right_intensity = int(base_intensity + right_wave * variation)

                elif pattern_style == "differential":
                    # Differential pattern for curve turns
                    # Both tracks active but at different intensities
                    left_wave = math.sin(elapsed * (2 * math.pi / cycle_time))
                    right_wave = math.sin(elapsed * (2 * math.pi / cycle_time) + 0.3)

                    left_intensity = int(
                        (base_intensity + left_wave * variation) * left_intensity_modifier
                    )
                    right_intensity = int(
                        (base_intensity + right_wave * variation) * right_intensity_modifier
                    )

                elif pattern_style == "alternating":
                    # Alternating pattern for spin turns - simulates tracks moving in opposite directions
                    # Use cosine for one side to create opposite effect
                    left_wave = math.sin(elapsed * (2 * math.pi / (cycle_time * 0.7)))
                    right_wave = -left_wave  # Opposite direction

                    left_intensity = int(
                        (base_intensity + left_wave * variation) * left_intensity_modifier
                    )
                    right_intensity = int(
                        (base_intensity + right_wave * variation) * right_intensity_modifier
                    )

                elif pattern_style == "pivot":
                    # Pivot pattern - one track stationary, one active
                    if turn_direction == TurnDirection.LEFT:
                        # Left pivot - minimal left track, strong right track
                        left_intensity = int(base_intensity * 0.2)  # Minimal rumble
                        right_intensity = int(
                            base_intensity
                            + math.sin(elapsed * (2 * math.pi / cycle_time)) * variation * 1.3
                        )
                    else:
                        # Right pivot - strong left track, minimal right track
                        left_intensity = int(
                            base_intensity
                            + math.sin(elapsed * (2 * math.pi / cycle_time)) * variation * 1.3
                        )
                        right_intensity = int(base_intensity * 0.2)  # Minimal rumble

                # Ensure values are within valid range
                left_intensity = max(0, min(65535, left_intensity))
                right_intensity = max(0, min(65535, right_intensity))

                # Force minimum intensity to ensure feedback is always felt on both sides
                left_intensity = (
                    max(8000, left_intensity) if left_intensity_modifier > 0.3 else left_intensity
                )
                right_intensity = (
                    max(8000, right_intensity)
                    if right_intensity_modifier > 0.3
                    else right_intensity
                )

                # Apply the rumble effect - explicitly identify which is which
                # The DualSense may map these differently than expected
                low_freq_motor = left_intensity  # This should be the left side/handle
                high_freq_motor = right_intensity  # This should be the right side/handle

                self.feedback.set_rumble(low_freq_motor, high_freq_motor, 50)

                # Short sleep to control update frequency
                time.sleep(0.04)  # Slightly faster update rate

        except Exception as e:
            print(f"Rumble error: {e}")
        finally:
            # Ensure rumble is stopped when thread ends
            self.feedback.set_rumble(0, 0, 0)

    def feedback_hit(self):
        """Provide feedback when tank is hit."""
        # Strong, sharp hit feedback
        self.set_rumble(65535, 65535, 300)

        # Flash LED red
        for _ in range(3):
            self.set_led_color(255, 0, 0)  # Red
            time.sleep(0.1)
            self.set_led_color(0, 0, 0)  # Off
            time.sleep(0.1)

    def feedback_flag_captured(self):
        """Provide feedback when flag is captured."""
        # Celebratory pulsing pattern
        self.pulse_rumble(intensity=32767, duration_sec=2, pattern_ms=200)

        # Flash LED green
        for _ in range(5):
            self.set_led_color(0, 255, 0)  # Green
            time.sleep(0.1)
            self.set_led_color(0, 0, 0)  # Off
            time.sleep(0.1)

    def feedback_flag_dropped(self):
        """Provide feedback when flag is dropped."""
        # Sad feedback - low intensity longer duration
        self.set_rumble(20000, 10000, 500)

        # Flash LED blue
        for _ in range(2):
            self.set_led_color(0, 0, 255)  # Blue
            time.sleep(0.2)
            self.set_led_color(0, 0, 0)  # Off
            time.sleep(0.2)

    def update_for_battery(self, battery_level: int) -> bool:
        """Update LED based on battery level.

        Args:
            battery_level: Battery percentage (0-100)

        Returns:
            bool: True if battery warning is active
        """
        if not self.initialized:
            return False

        # Handle low battery warning
        if battery_level <= BATTERY_CRITICAL_LEVEL:
            # Critical battery - fast red flashing
            if time.time() % 0.6 < 0.3:  # Fast flashing
                self.set_led_color(255, 0, 0)  # Bright red
            else:
                self.set_led_color(50, 0, 0)  # Dim red
            return True
        elif battery_level <= BATTERY_WARNING_LEVEL:
            # Low battery - slow orange pulsing
            if time.time() % 2 < 1:  # Slow pulsing
                self.set_led_color(255, 128, 0)  # Orange
            else:
                self.set_led_color(50, 25, 0)  # Dim orange
            return True

        return False
