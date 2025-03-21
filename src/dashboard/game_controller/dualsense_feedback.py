"""
DualSense Feedback Extension Module with improved rumble control
Adds rumble and LED support to the DualSense controller integration.
"""

import logging
import threading
import time
from typing import Any, Dict, Optional, Tuple

# Try to import SDL2 dependencies, but allow fallback if not available
try:
    import sdl2
    import sdl2.ext

    SDL2_AVAILABLE = True
except ImportError:
    SDL2_AVAILABLE = False

logger = logging.getLogger(__name__)


class DualSenseFeedback:
    """Class to add rumble and LED functionality to DualSense controller."""

    # Speed mode color mapping
    SPEED_MODE_COLORS = {
        0: (0, 255, 0),  # Low speed: Green
        1: (255, 255, 0),  # Medium speed: Yellow
        2: (255, 0, 0),  # High speed: Red
    }

    # Battery level color mapping
    BATTERY_WARNING_LEVEL = 20  # Percentage
    BATTERY_CRITICAL_LEVEL = 10  # Percentage

    def __init__(self):
        """Initialize the DualSense feedback controller."""
        self.sdl_controller = None
        self.joystick = None
        self.haptic = None
        self.initialized = False
        self.controller_name = ""
        self._rumble_thread = None
        self._stop_rumble = threading.Event()
        self._rumble_timer = None  # For short duration rumbles

        # Initialize SDL if available
        if SDL2_AVAILABLE:
            self._initialize_sdl()
        else:
            logger.warning("SDL2 not available - LED and rumble features disabled")

    def _initialize_sdl(self):
        """Initialize SDL2 for DualSense feedback features."""
        try:
            # Initialize SDL2 with required subsystems
            if sdl2.SDL_Init(sdl2.SDL_INIT_GAMECONTROLLER | sdl2.SDL_INIT_HAPTIC) != 0:
                error = sdl2.SDL_GetError().decode("utf-8")
                logger.error(f"SDL2 initialization failed: {error}")
                return False

            # Look for DualSense controller
            num_joysticks = sdl2.SDL_NumJoysticks()
            if num_joysticks == 0:
                logger.warning("No controllers detected for SDL2")
                sdl2.SDL_Quit()
                return False

            # Try to find and open a DualSense controller
            for i in range(num_joysticks):
                if not sdl2.SDL_IsGameController(i):
                    continue

                temp_controller = sdl2.SDL_GameControllerOpen(i)
                if not temp_controller:
                    continue

                try:
                    name = sdl2.SDL_GameControllerName(temp_controller).decode("utf-8")

                    # Check if it's a DualSense
                    if "DualSense" in name:
                        self.sdl_controller = temp_controller
                        self.controller_name = name

                        # Initialize haptic feedback if available
                        joystick = sdl2.SDL_GameControllerGetJoystick(self.sdl_controller)
                        self.haptic = sdl2.SDL_HapticOpenFromJoystick(joystick)

                        self.initialized = True
                        logger.info(f"SDL2 initialized for DualSense feedback: {name}")
                        return True
                    else:
                        # Close if not a DualSense
                        sdl2.SDL_GameControllerClose(temp_controller)
                except Exception as e:
                    logger.error(f"Error determining controller name: {e}")
                    sdl2.SDL_GameControllerClose(temp_controller)

            logger.warning("No DualSense controller found for SDL2")
            sdl2.SDL_Quit()
            return False

        except Exception as e:
            logger.error(f"Error initializing SDL2: {e}")
            return False

    def set_led_color(self, r: int, g: int, b: int) -> bool:
        """Set the controller LED color.

        Args:
            r, g, b: Color values (0-255)

        Returns:
            bool: Success or failure
        """
        if not self.initialized or not self.sdl_controller:
            return False

        try:
            result = sdl2.SDL_GameControllerSetLED(self.sdl_controller, r, g, b)
            return result == 0
        except AttributeError:
            logger.warning("LED control not supported in this SDL2 version")
            return False

    def set_rumble(self, low_freq: int = 0, high_freq: int = 0, duration_ms: int = 0) -> bool:
        """Set rumble effect with improved duration handling.

        Args:
            low_freq: Low frequency rumble intensity (0-65535)
            high_freq: High frequency rumble intensity (0-65535)
            duration_ms: Duration in milliseconds (0 = continuous until stopped)

        Returns:
            bool: Success or failure
        """
        if not self.initialized or not self.sdl_controller:
            return False

        # Cancel any existing rumble timer
        if self._rumble_timer:
            self._rumble_timer.cancel()
            self._rumble_timer = None

        try:
            # Start the rumble with a very long duration or continuous
            if low_freq == 0 and high_freq == 0:
                # Just stopping the rumble
                result = sdl2.SDL_GameControllerRumble(self.sdl_controller, 0, 0, 0)
                return result == 0

            # For non-zero rumble
            if duration_ms > 0:
                # Start rumble continuously - we'll stop it after the duration
                result = sdl2.SDL_GameControllerRumble(
                    self.sdl_controller, low_freq, high_freq, 0  # Continuous
                )

                # Schedule a timer to stop the rumble after the requested duration
                if result == 0:
                    # Convert ms to seconds for the timer
                    duration_sec = max(duration_ms / 1000.0, 0.001)  # Minimum 1ms
                    self._rumble_timer = threading.Timer(
                        duration_sec,
                        lambda: sdl2.SDL_GameControllerRumble(self.sdl_controller, 0, 0, 0),
                    )
                    self._rumble_timer.daemon = True
                    self._rumble_timer.start()
            else:
                # Continuous rumble
                result = sdl2.SDL_GameControllerRumble(
                    self.sdl_controller, low_freq, high_freq, 0  # Continuous
                )

            return result == 0
        except AttributeError:
            # Fall back to haptic if available
            if self.haptic:
                return self._set_haptic_rumble(low_freq, high_freq, duration_ms)
            logger.warning("Rumble not supported")
            return False

    def _set_haptic_rumble(self, low_freq: int, high_freq: int, duration_ms: int) -> bool:
        """Alternative method using haptic interface with improved handling."""
        if not self.haptic:
            return False

        try:
            import ctypes

            # Convert 0-65535 to 0-32767 for SDL haptic
            low = min(32767, int(low_freq / 2))
            high = min(32767, int(high_freq / 2))

            # For zero vibration, just stop effects
            if low == 0 and high == 0:
                sdl2.SDL_HapticStopAll(self.haptic)
                return True

            # For non-zero vibration
            effect = sdl2.SDL_HapticEffect()
            effect.type = sdl2.SDL_HAPTIC_LEFTRIGHT

            # Use continuous effect for very short durations, we'll manage timing
            if duration_ms <= 10:
                effect.leftright.length = 0  # Continuous
            else:
                effect.leftright.length = max(1, duration_ms)

            effect.leftright.large_magnitude = low
            effect.leftright.small_magnitude = high

            effect_id = sdl2.SDL_HapticNewEffect(self.haptic, ctypes.byref(effect))
            if effect_id >= 0:
                sdl2.SDL_HapticRunEffect(self.haptic, effect_id, 1)

                # For very short durations, manually stop after the requested time
                if duration_ms > 0 and duration_ms <= 10:
                    # Use a timer to stop the effect
                    threading.Timer(
                        duration_ms / 1000.0,
                        lambda: (
                            sdl2.SDL_HapticStopEffect(self.haptic, effect_id),
                            sdl2.SDL_HapticDestroyEffect(self.haptic, effect_id),
                        ),
                    ).start()
                elif duration_ms > 10:
                    # Auto cleanup after duration for longer effects
                    threading.Timer(
                        duration_ms / 1000.0,
                        lambda: sdl2.SDL_HapticDestroyEffect(self.haptic, effect_id),
                    ).start()

                return True

            return False
        except Exception as e:
            logger.error(f"Error setting haptic rumble: {e}")
            return False

    def pulse_rumble(
        self, intensity: int = 32767, duration_sec: float = 5, pattern_ms: int = 500
    ) -> bool:
        """Create a pulsing rumble effect.

        Args:
            intensity: Rumble intensity (0-65535)
            duration_sec: Total duration in seconds
            pattern_ms: Pattern duration in milliseconds

        Returns:
            bool: Success or failure
        """
        if not self.initialized or not self.sdl_controller:
            return False

        # Stop any existing rumble thread
        self.stop_rumble()

        # Create a new thread for pulsing
        self._stop_rumble.clear()
        self._rumble_thread = threading.Thread(
            target=self._pulse_rumble_thread, args=(intensity, duration_sec, pattern_ms)
        )
        self._rumble_thread.daemon = True
        self._rumble_thread.start()
        return True

    def _pulse_rumble_thread(self, intensity: int, duration_sec: float, pattern_ms: int):
        """Thread function for pulsing rumble."""
        start_time = time.time()

        while not self._stop_rumble.is_set():
            # Check if total duration has elapsed
            if duration_sec > 0 and (time.time() - start_time) > duration_sec:
                break

            # Rumble on - use manual timing for short durations
            on_duration = max(50, pattern_ms // 2)  # Minimum 50ms for better perception
            self.set_rumble(intensity, intensity, on_duration)

            # Sleep slightly less than the rumble duration to minimize gaps
            sleep_time = on_duration / 1000.0 * 0.8  # 80% of the on duration
            time.sleep(sleep_time)

            # Check if we should stop
            if self._stop_rumble.is_set():
                break

            # Explicit rumble off
            self.set_rumble(0, 0, 0)

            # Sleep for off duration
            off_duration = pattern_ms / 2000.0
            time.sleep(off_duration)

        # Ensure rumble is off
        self.set_rumble(0, 0, 0)

    def stop_rumble(self):
        """Stop any active rumble effects."""
        # Cancel any rumble timer
        if self._rumble_timer and self._rumble_timer.is_alive():
            self._rumble_timer.cancel()
            self._rumble_timer = None

        # Stop pulsing thread if running
        if self._rumble_thread and self._rumble_thread.is_alive():
            self._stop_rumble.set()
            self._rumble_thread.join(timeout=1.0)

        # Make sure rumble is off
        if self.initialized and self.sdl_controller:
            self.set_rumble(0, 0, 0)

    def trigger_quick_feedback(self, intensity=40000, duration_ms=100):
        """Provide a quick rumble feedback that is clearly noticeable.

        Args:
            intensity: Rumble intensity (default: 40000)
            duration_ms: Duration in milliseconds (default: 100ms)

        Returns:
            bool: Success or failure
        """
        # Use both motors for clear feedback
        return self.set_rumble(intensity, intensity, duration_ms)

    def update_for_speed(self, speed_mode: int, speed: float) -> None:
        """Update LED and rumble based on current speed.

        Args:
            speed_mode: Current speed mode (0, 1, 2)
            speed: Current speed value (0-100)
        """
        if not self.initialized:
            return

        # Set LED color based on speed mode
        if speed_mode in self.SPEED_MODE_COLORS:
            self.set_led_color(*self.SPEED_MODE_COLORS[speed_mode])

        # Base rumble intensity on actual speed
        if speed > 0:
            # Calculate intensity based on speed percentage
            intensity = int(
                (speed / 100.0) * 20000
            )  # Lower base intensity to avoid excessive rumble

            # Different rumble patterns for different speed modes
            if speed_mode == 0:  # Low speed
                # Gentle, low-frequency rumble for low speed
                self.set_rumble(intensity, intensity // 4, 100)
            elif speed_mode == 1:  # Medium speed
                # Balanced rumble for medium speed
                self.set_rumble(intensity, intensity // 2, 100)
            elif speed_mode == 2:  # High speed
                # More intense, higher-frequency rumble for high speed
                self.set_rumble(intensity // 2, intensity, 100)

    def update_for_turning(self, turn_direction: str, turn_factor: float, speed: float) -> None:
        """Update rumble based on turning.

        Args:
            turn_direction: Direction of turn ('left', 'right', 'none')
            turn_factor: Turning factor (0.0-1.0)
            speed: Current speed value (0-100)
        """
        if not self.initialized or turn_direction == "none":
            return

        # Calculate base intensity from speed
        base_intensity = int((speed / 100.0) * 32768)

        # Scale by turn factor
        turn_intensity = int(base_intensity * turn_factor * 1.5)  # Amplify turning feedback
        base_intensity = min(turn_intensity, 65535)  # Cap at max value

        # Asymmetric rumble based on turn direction
        if turn_direction == "left":
            # Stronger rumble on left motor when turning left
            self.set_rumble(base_intensity, base_intensity // 3, 100)
        elif turn_direction == "right":
            # Stronger rumble on right motor when turning right
            self.set_rumble(base_intensity // 3, base_intensity, 100)

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
        if battery_level <= self.BATTERY_CRITICAL_LEVEL:
            # Critical battery - fast red flashing
            if time.time() % 0.6 < 0.3:  # Fast flashing
                self.set_led_color(255, 0, 0)  # Bright red
            else:
                self.set_led_color(50, 0, 0)  # Dim red
            return True
        elif battery_level <= self.BATTERY_WARNING_LEVEL:
            # Low battery - slow orange pulsing
            if time.time() % 2 < 1:  # Slow pulsing
                self.set_led_color(255, 128, 0)  # Orange
            else:
                self.set_led_color(50, 25, 0)  # Dim orange
            return True

        return False

    def cleanup(self):
        """Clean up resources."""
        self.stop_rumble()

        # Cancel any rumble timer
        if self._rumble_timer and self._rumble_timer.is_alive():
            self._rumble_timer.cancel()
            self._rumble_timer = None

        if self.haptic:
            sdl2.SDL_HapticClose(self.haptic)
            self.haptic = None

        if self.sdl_controller:
            sdl2.SDL_GameControllerClose(self.sdl_controller)
            self.sdl_controller = None

        if self.initialized:
            sdl2.SDL_Quit()
            self.initialized = False
