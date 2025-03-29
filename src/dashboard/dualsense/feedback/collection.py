"""This module holds an optimized collection of feedback mechanisms for the Dualsense controller."""

import math
import threading
import time
from enum import Enum, auto

from src.common.constants.controller import BATTERY_CRITICAL_LEVEL, BATTERY_WARNING_LEVEL
from src.common.constants.game import FLAG_CAPTURE_DURATION
from src.common.enum.movement import (
    CurvedTurnRate,
    SpeedMode,
    ThrustDirection,
    TurnDirection,
    TurnType,
)
from src.common.logging.logger_api import Logger
from src.dashboard.dualsense.feedback.feedback_main import DualSenseFeedback


class FeedbackType(Enum):
    """Types of feedback events that can be queued."""

    SPEED_OUT_OF_BOUND = auto()
    SPEED_CHANGE = auto()
    MOVE = auto()
    STOP_RUMBLE = auto()
    SHOOT = auto()
    HIT_BY_SHOT = auto()
    CAPTURE_FLAG = auto()
    FLAG_CAPTURED = auto()
    FLAG_CAPTURE_FAILED = auto()
    PIVOT_MODE = auto()
    UPDATE_BATTERY = auto()
    SET_LED = auto()


class DualsenseFeedbackCollection:
    def __init__(self, dualsense_feedback_collection_logger: Logger, feedback: DualSenseFeedback):
        self.logger = dualsense_feedback_collection_logger
        self.logger.infow("Initializing Dualsense feedback collection")

        self.feedback = feedback
        self.is_flag_capturing = False

        # Current LED color (to restore after effects)
        self.current_led_color = (0, 0, 0)  # Default color (r, g, b)

        # For background tasks that need to run in threads
        self._running = True
        self._rumble_active = False

        # Lock for thread safety when modifying shared state
        self._lock = threading.Lock()

        # Current active rumble thread (for movement)
        self._active_rumble_thread = None

        self.logger.infow("Dualsense feedback collection initialized")

    def shutdown(self) -> None:
        """Shuts down the feedback collection."""
        self._running = False
        self._rumble_active = False
        self.feedback.stop_rumble()
        self.logger.infow("Dualsense feedback collection shutdown")

    # --- Public API (Mostly synchronous for immediate feedback) ---

    def on_speed_out_of_bound(self, r: int, g: int, b: int) -> None:
        """Provide immediate feedback when speed is out of bounds."""
        # Store the requested LED color
        self.current_led_color = (r, g, b)

        # Provide immediate feedback
        self.feedback.set_rumble(65535, 65535, 200)
        self.feedback.set_led_color(r, g, b)

        # Run the flash effect in a separate thread to not block
        threading.Thread(target=self._run_speed_bound_effect, args=(r, g, b), daemon=True).start()

    def _run_speed_bound_effect(self, r: int, g: int, b: int):
        """Run the speed bound effect in background thread."""
        for _ in range(2):  # Reduced to 2 flashes for quicker response
            if not self._running:
                break

            time.sleep(0.15)
            self.feedback.set_rumble(0, 0, 200)
            self.feedback.set_led_color(0, 0, 0)  # Off
            time.sleep(0.15)
            self.feedback.set_rumble(65535, 65535, 200)
            self.feedback.set_led_color(r, g, b)

        # One final pulse to ensure it ends in the right state
        time.sleep(0.1)
        # Restore the LED color
        self.feedback.set_led_color(r, g, b)

    def on_speed_change(self, r: int, g: int, b: int) -> None:
        """Provide immediate feedback when speed changes."""
        # Store the requested LED color and update immediately
        self.current_led_color = (r, g, b)
        self.feedback.set_led_color(r, g, b)

        # Short, immediate rumble feedback
        self.feedback.set_rumble(15000, 15000, 150)

    def on_move(
        self,
        thrust_direction: ThrustDirection,
        turn_direction: TurnDirection,
        turn_type: TurnType,
        speed: SpeedMode,
        curved_turn_rate: CurvedTurnRate,
    ) -> None:
        """Provide movement feedback with improved synchronization."""
        if thrust_direction == ThrustDirection.NONE and turn_direction == TurnDirection.NONE:
            self.stop_rumble()
            return

        # Stop existing rumble thread
        with self._lock:
            self._rumble_active = False
            if self._active_rumble_thread and self._active_rumble_thread.is_alive():
                # Give the thread a moment to shut down
                time.sleep(0.02)

        # Start a new thread for continuous rumble
        with self._lock:
            self._rumble_active = True
            self._active_rumble_thread = threading.Thread(
                target=self._continuous_rumble,
                args=(thrust_direction, turn_direction, turn_type, speed, curved_turn_rate),
                daemon=True,
            )
            self._active_rumble_thread.start()

    def stop_rumble(self) -> None:
        """Stop rumble with improved synchronization."""
        with self._lock:
            self._rumble_active = False

        # Immediately stop the rumble effect
        self.feedback.set_rumble(0, 0, 0)

        # Give any active thread a moment to shut down
        time.sleep(0.01)

    def on_shoot(self) -> None:
        """Provide immediate feedback when tank shoots."""
        # Store current LED color
        r, g, b = self.current_led_color

        # Immediate strong rumble effect
        self.feedback.set_rumble(50000, 50000, 200)

        # Flash LED red
        self.feedback.set_led_color(255, 0, 0)  # Red

        # Restore color after a short delay (in thread to not block)
        def restore_color():
            time.sleep(0.15)
            self.feedback.set_led_color(r, g, b)

        threading.Thread(target=restore_color, daemon=True).start()

    def on_hit_by_shot(self) -> None:
        """Provide feedback when tank is hit by a shot."""
        # Store current LED color
        r, g, b = self.current_led_color

        # Immediate strong rumble
        self.feedback.set_rumble(65535, 65535, 300)

        # Start the effect in a background thread
        threading.Thread(target=self._hit_effect, args=(r, g, b), daemon=True).start()

    def _hit_effect(self, r: int, g: int, b: int):
        """Run the hit effect in a background thread."""
        # Flash LED red and vibrate
        start_time = time.time()
        elapsed_time = 0

        # Flash for up to 1.5 seconds (reduced from 2s for quicker response)
        while elapsed_time < 1.5 and self._running:
            progress = elapsed_time / 1.5  # Progression from 0 to 1

            # Interpolate color from red to original
            flash_r = int(255 * (1 - progress) + r * progress)
            flash_g = int(0 * (1 - progress) + g * progress)
            flash_b = int(0 * (1 - progress) + b * progress)

            self.feedback.set_led_color(flash_r, flash_g, flash_b)
            self.feedback.set_rumble(65535 * (1 - progress), 65535 * (1 - progress), 100)
            time.sleep(0.1)

            if not self._running:
                break

            self.feedback.set_led_color(0, 0, 0)  # Off
            time.sleep(0.05)

            elapsed_time = time.time() - start_time

        # Restore LED to previous color
        self.feedback.set_led_color(r, g, b)
        self.feedback.set_rumble(0, 0, 0)

    def on_capture_flag(self) -> None:
        """Feedback when flag capture starts."""
        # Store purple color for flag capture (This avoids flickering)
        r, g, b = (255, 0, 255)  # Default color for flag capture

        # Set capturing flag immediately for other methods to check
        self.is_flag_capturing = True

        # Start the flag capture feedback in a separate thread
        threading.Thread(target=self._capture_flag_feedback, args=(r, g, b), daemon=True).start()

    def _capture_flag_feedback(self, r: int, g: int, b: int):
        """Run flag capture feedback in a background thread."""
        start_time = time.time()

        # Run flag capture feedback loop
        while (
            time.time() - start_time < FLAG_CAPTURE_DURATION
            and self.is_flag_capturing
            and self._running
        ):
            self.feedback.set_led_color(255, 0, 255)  # Purple
            self.feedback.set_rumble(20000, 20000, 100)
            time.sleep(0.1)

            if not self.is_flag_capturing or not self._running:
                break

            self.feedback.set_led_color(0, 0, 0)
            self.feedback.set_rumble(0, 0, 100)
            time.sleep(0.1)

        # Set final color only if still capturing
        if self.is_flag_capturing and self._running:
            self.feedback.set_led_color(255, 0, 255)  # Purple
        else:
            # Restore original color if capture interrupted
            self.feedback.set_led_color(r, g, b)

    def on_flag_captured(self) -> None:
        """Feedback when flag is captured."""
        # Store current LED color
        r, g, b = self.current_led_color

        # Set flag capturing to false
        self.is_flag_capturing = False

        # Immediate feedback
        self.feedback.set_led_color(0, 255, 0)  # Green
        self.feedback.set_rumble(65535, 65535, 200)

        # Start victory effect in thread
        threading.Thread(target=self._flag_captured_effect, args=(r, g, b), daemon=True).start()

    def _flag_captured_effect(self, r: int, g: int, b: int):
        """Run flag captured effect in background thread."""
        # Flash green a few times
        for _ in range(4):  # Reduced from 5 for quicker response
            if not self._running:
                break

            time.sleep(0.1)
            self.feedback.set_led_color(0, 0, 0)  # Off
            self.feedback.set_rumble(0, 0, 100)
            time.sleep(0.1)
            self.feedback.set_led_color(0, 255, 0)  # Green
            self.feedback.set_rumble(65535, 65535, 100)

        # Restore LED to previous color
        self.feedback.set_led_color(r, g, b)
        self.feedback.set_rumble(0, 0, 0)

    def on_flag_capture_failed(self) -> None:
        """Feedback when flag capture fails."""
        # Store current LED color
        r, g, b = self.current_led_color

        # Immediately set flag to ensure other processes know we're done
        self.is_flag_capturing = False

        # Immediate feedback
        self.feedback.set_led_color(255, 0, 0)  # Red
        self.feedback.set_rumble(65535, 65535, 200)

        # Start fail effect in background
        threading.Thread(
            target=self._flag_capture_failed_effect, args=(r, g, b), daemon=True
        ).start()

    def _flag_capture_failed_effect(self, r: int, g: int, b: int):
        """Run flag capture failed effect in background thread."""
        for _ in range(1):  # Just one flash for quicker response
            if not self._running:
                break

            time.sleep(0.2)
            self.feedback.set_led_color(0, 0, 0)  # Off
            time.sleep(0.1)
            self.feedback.set_led_color(255, 0, 0)  # Red
            self.feedback.set_rumble(65535, 65535, 200)

        # Restore LED to previous color after a short delay
        time.sleep(0.3)
        self.feedback.set_led_color(r, g, b)
        self.feedback.set_rumble(0, 0, 0)

    def on_pivot_mode(self) -> None:
        """Feedback when pivot mode is activated."""
        # Store current LED color
        r, g, b = self.current_led_color

        # Immediate feedback
        self.feedback.set_led_color(255, 255, 0)  # Yellow
        self.feedback.set_rumble(30000, 30000, 150)

        # Start effect in background
        threading.Thread(target=self._pivot_mode_effect, args=(r, g, b), daemon=True).start()

    def _pivot_mode_effect(self, r: int, g: int, b: int):
        """Run pivot mode effect in background thread."""
        # Flash yellow a few times
        for _ in range(3):  # Reduced from 5 for quicker response
            if not self._running:
                break

            time.sleep(0.1)
            self.feedback.set_led_color(0, 0, 0)  # Off
            self.feedback.set_rumble(0, 0, 100)
            time.sleep(0.05)
            self.feedback.set_led_color(255, 255, 0)  # Yellow
            self.feedback.set_rumble(30000, 30000, 100)

        # Restore LED to previous color
        time.sleep(0.1)
        self.feedback.set_led_color(r, g, b)
        self.feedback.set_rumble(0, 0, 0)

    def update_for_battery(self, battery_level: int) -> bool:
        """Update LED based on battery level."""
        if not self.feedback.initialized:
            return False

        # Store current LED color if not in warning state
        if battery_level > BATTERY_WARNING_LEVEL:
            r, g, b = self.current_led_color
            self.feedback.set_led_color(r, g, b)
            return False

        # Handle low battery warning with immediate feedback
        self._handle_update_battery(battery_level)
        return battery_level <= BATTERY_WARNING_LEVEL

    def set_led_color(self, r: int, g: int, b: int) -> None:
        """Set the LED color with immediate feedback."""
        self.current_led_color = (r, g, b)
        self.feedback.set_led_color(r, g, b)

    # --- Private implementation details ---

    def _continuous_rumble(
        self,
        thrust_direction: ThrustDirection,
        turn_direction: TurnDirection,
        turn_type: TurnType,
        speed: SpeedMode,
        curved_turn_rate: CurvedTurnRate,
    ) -> None:
        """Create a continuous rumble pattern that simulates realistic tank movement."""
        try:
            # Base configuration based on speed
            if speed == SpeedMode.STOP:
                base_intensity = 0
                variation = 0
                cycle_time = 1
            elif speed == SpeedMode.GEAR_1:  # 70%
                base_intensity = 20000
                variation = 10000
                cycle_time = 0.5  # Reduced from 0.7 for more responsive feel
            elif speed == SpeedMode.GEAR_2:  # 80%
                base_intensity = 30000
                variation = 15000
                cycle_time = 0.4  # Reduced from 0.6
            elif speed == SpeedMode.GEAR_3:  # 90%
                base_intensity = 40000
                variation = 20000
                cycle_time = 0.3  # Reduced from 0.5
            elif speed == SpeedMode.GEAR_4:  # 100%
                base_intensity = 50000
                variation = 25000
                cycle_time = 0.2  # Reduced from 0.4
            else:
                raise ValueError("Invalid speed mode")

            # Default pattern (straight movement)
            left_intensity_modifier = 1.0
            right_intensity_modifier = 1.0
            pattern_style = "continuous"  # Default pattern

            # Apply thrust direction modifiers
            thrust_modifier = 1.0
            if thrust_direction == ThrustDirection.FORWARD:
                # Forward thrust feels slightly stronger
                thrust_modifier = 1.2
                # Tank tracks have slightly different patterns when moving forward for realism
                phase_difference = 0.3  # Reduced from 0.6 for quicker response
            elif thrust_direction == ThrustDirection.BACKWARD:
                # Backward thrust has a different feel
                thrust_modifier = 1.0
                # Different phase for reverse movement
                phase_difference = 0.4  # Reduced from 0.8
                # Slightly slower cycle for reverse
                cycle_time *= 1.1  # Reduced from 1.2
            else:  # NONE
                thrust_modifier = 0.9
                phase_difference = 0.25  # Reduced from 0.5

            # Apply thrust modifier to base values
            base_intensity = int(base_intensity * thrust_modifier)

            # Patterns for different turn types with thrust direction considerations
            if turn_direction != TurnDirection.NONE:
                if turn_type == TurnType.CURVE:
                    # For curve turns - one track moves faster than the other
                    pattern_style = "differential"
                    curve_strength = curved_turn_rate.value if curved_turn_rate else 0.5

                    if turn_direction == TurnDirection.LEFT:
                        # Left turn - right track moves faster
                        left_intensity_modifier = max(0.3, 1.0 - curve_strength * 0.8)
                        right_intensity_modifier = min(2.0, 1.0 + curve_strength * 0.8)

                        # Apply thrust direction to curve feel
                        if thrust_direction == ThrustDirection.FORWARD:
                            # Forward left curve has specific pattern
                            right_intensity_modifier *= 1.2  # Outer track more pronounced
                        elif thrust_direction == ThrustDirection.BACKWARD:
                            # Backward left curve feels different
                            left_intensity_modifier *= 1.1  # Inner track more pronounced in reverse

                    else:  # RIGHT
                        # Right turn - left track moves faster
                        left_intensity_modifier = min(2.0, 1.0 + curve_strength * 0.8)
                        right_intensity_modifier = max(0.3, 1.0 - curve_strength * 0.8)

                        # Apply thrust direction to curve feel
                        if thrust_direction == ThrustDirection.FORWARD:
                            # Forward right curve has specific pattern
                            left_intensity_modifier *= 1.2  # Outer track more pronounced
                        elif thrust_direction == ThrustDirection.BACKWARD:
                            # Backward right curve feels different
                            right_intensity_modifier *= (
                                1.1  # Inner track more pronounced in reverse
                            )

                elif turn_type == TurnType.SPIN:
                    # For spin turns - one track forward, one backward
                    pattern_style = "alternating"

                    # Spin patterns affected by thrust direction
                    if thrust_direction == ThrustDirection.NONE:
                        # Pure spin (no thrust) - balanced intensity
                        left_intensity_modifier = 1.5
                        right_intensity_modifier = 1.5
                        # Pure spins have faster oscillation
                        cycle_time *= 0.5  # Reduced from 0.8 for quicker response
                    else:
                        # Thrusting spin - uneven intensities
                        if turn_direction == TurnDirection.LEFT:
                            left_intensity_modifier = 1.3
                            right_intensity_modifier = 1.7
                        else:  # RIGHT
                            left_intensity_modifier = 1.7
                            right_intensity_modifier = 1.3

                elif turn_type == TurnType.PIVOT:
                    # For pivot turns - one track stationary, one moves
                    pattern_style = "pivot"

                    # Pivot affected by thrust direction
                    if thrust_direction != ThrustDirection.NONE:
                        # Moving pivot has different feel than stationary pivot
                        pivot_intensity = 2.0  # Stronger pivot when thrusting
                    else:
                        pivot_intensity = 1.8

                    if turn_direction == TurnDirection.LEFT:
                        # Left pivot - right track moves, left stationary
                        left_intensity_modifier = 0.15
                        right_intensity_modifier = pivot_intensity
                    else:  # RIGHT
                        # Right pivot - left track moves, right stationary
                        left_intensity_modifier = pivot_intensity
                        right_intensity_modifier = 0.15

            # IMMEDIATE INITIAL FEEDBACK - give immediate strong rumble at start
            # Pattern depends on both thrust and turn type
            initial_left = base_intensity * left_intensity_modifier * 1.3
            initial_right = base_intensity * right_intensity_modifier * 1.3

            # Special case for thrust with no turning
            if thrust_direction != ThrustDirection.NONE and turn_direction == TurnDirection.NONE:
                if thrust_direction == ThrustDirection.FORWARD:
                    # Stronger initial forward thrust
                    initial_left *= 1.2
                    initial_right *= 1.2
                else:  # BACKWARD
                    # Distinct backward startup feel
                    initial_left *= 1.1
                    initial_right *= 1.1

            self.feedback.set_rumble(int(initial_left), int(initial_right), 80)

            # Main rumble loop with thrust direction incorporated
            start_time = time.time()
            update_rate = 0.01  # 100Hz updates for more responsive feel (reduced from 0.03)

            while self._rumble_active and self._running:
                elapsed = time.time() - start_time

                # Calculate primary oscillation patterns
                # Base pattern varies by thrust direction
                if thrust_direction == ThrustDirection.FORWARD:
                    # Forward movement oscillation
                    primary_wave_l = math.sin(elapsed * (2 * math.pi / cycle_time))
                    primary_wave_r = math.sin(
                        elapsed * (2 * math.pi / cycle_time) + phase_difference
                    )
                elif thrust_direction == ThrustDirection.BACKWARD:
                    # Backward movement has different feel - cosine creates different curve shape
                    primary_wave_l = math.cos(elapsed * (2 * math.pi / cycle_time))
                    primary_wave_r = math.cos(
                        elapsed * (2 * math.pi / cycle_time) + phase_difference
                    )
                else:  # NONE - when only turning
                    # Pure turning has simpler pattern
                    primary_wave_l = math.sin(elapsed * (2 * math.pi / cycle_time))
                    primary_wave_r = math.sin(
                        elapsed * (2 * math.pi / cycle_time) + phase_difference
                    )

                # Apply different patterns based on movement type
                if pattern_style == "continuous":
                    # Standard continuous pattern for straight movement
                    left_intensity = int(base_intensity + primary_wave_l * variation)
                    right_intensity = int(base_intensity + primary_wave_r * variation)

                    # For pure thrust (no turning), add special patterns
                    if (
                        turn_direction == TurnDirection.NONE
                        and thrust_direction != ThrustDirection.NONE
                    ):
                        # Add subtle tank track oscillation effect
                        track_effect = (
                            math.sin(elapsed * (2 * math.pi / (cycle_time * 0.25)))
                            * variation
                            * 0.3
                        )

                        if thrust_direction == ThrustDirection.FORWARD:
                            left_intensity += int(track_effect)
                            right_intensity -= int(track_effect)
                        else:  # BACKWARD
                            left_intensity -= int(track_effect)
                            right_intensity += int(track_effect)

                elif pattern_style == "differential":
                    # Differential pattern for curve turns
                    left_intensity = int(
                        (base_intensity + primary_wave_l * variation) * left_intensity_modifier
                    )
                    right_intensity = int(
                        (base_intensity + primary_wave_r * variation) * right_intensity_modifier
                    )

                elif pattern_style == "alternating":
                    # Alternating pattern for spin turns
                    # Different pattern based on thrust
                    if thrust_direction == ThrustDirection.NONE:
                        # Pure spin effect
                        left_wave = math.sin(elapsed * (2 * math.pi / (cycle_time * 0.6)))
                        right_wave = -left_wave  # Opposite direction
                    else:
                        # Spinning while thrusting - more complex pattern
                        left_wave = math.sin(elapsed * (2 * math.pi / (cycle_time * 0.7)))
                        right_wave = -math.sin(
                            elapsed * (2 * math.pi / (cycle_time * 0.7)) + 0.2
                        )  # Slight phase shift

                    left_intensity = int(
                        (base_intensity + left_wave * variation) * left_intensity_modifier
                    )
                    right_intensity = int(
                        (base_intensity + right_wave * variation) * right_intensity_modifier
                    )

                elif pattern_style == "pivot":
                    # Pivot pattern - one track stationary, one active
                    # Pivot feel depends on thrust direction
                    pivot_speed = cycle_time
                    if thrust_direction != ThrustDirection.NONE:
                        # Moving pivot has faster oscillation
                        pivot_speed *= 0.8

                    if turn_direction == TurnDirection.LEFT:
                        # Left pivot - minimal left track, strong right track
                        left_intensity = int(base_intensity * 0.1)
                        right_intensity = int(
                            base_intensity
                            + math.sin(elapsed * (2 * math.pi / pivot_speed)) * variation * 1.5
                        )
                    else:
                        # Right pivot - strong left track, minimal right track
                        left_intensity = int(
                            base_intensity
                            + math.sin(elapsed * (2 * math.pi / pivot_speed)) * variation * 1.5
                        )
                        right_intensity = int(base_intensity * 0.1)

                # Ensure values are within valid range
                left_intensity = max(0, min(65535, left_intensity))
                right_intensity = max(0, min(65535, right_intensity))

                # Ensure feedback always feels present
                left_intensity = (
                    max(10000, left_intensity) if left_intensity_modifier > 0.2 else left_intensity
                )
                right_intensity = (
                    max(10000, right_intensity)
                    if right_intensity_modifier > 0.2
                    else right_intensity
                )

                # Apply the rumble effect
                low_freq_motor = left_intensity  # Left side/handle
                high_freq_motor = right_intensity  # Right side/handle

                # Check if thread should still be running
                if not self._rumble_active or not self._running:
                    break

                # Apply rumble with shorter duration for more responsive updates
                self.feedback.set_rumble(low_freq_motor, high_freq_motor, 50)

                # Shorter sleep for more responsive updates
                time.sleep(update_rate)

        except Exception as e:
            self.logger.errorw("Rumble error", "error", str(e))
        finally:
            # Ensure rumble is stopped when thread ends
            self.feedback.set_rumble(0, 0, 0)

    def _handle_update_battery(self, battery_level: int) -> None:
        """Immediately update LED based on battery level."""
        if not self.feedback.initialized:
            return

        # Handle low battery warning with immediate visual feedback
        if battery_level <= BATTERY_CRITICAL_LEVEL:
            # Critical battery - red flashing
            if time.time() % 0.6 < 0.3:  # Fast flashing
                self.feedback.set_led_color(255, 0, 0)  # Bright red
            else:
                self.feedback.set_led_color(50, 0, 0)  # Dim red
        elif battery_level <= BATTERY_WARNING_LEVEL:
            # Low battery - orange pulsing
            if time.time() % 2 < 1:  # Slow pulsing
                self.feedback.set_led_color(255, 128, 0)  # Orange
            else:
                self.feedback.set_led_color(50, 25, 0)  # Dim orange
