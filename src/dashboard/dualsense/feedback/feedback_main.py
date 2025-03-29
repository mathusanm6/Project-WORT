"""
DualSense Feedback Extension Module with improved rumble control
Adds rumble and LED support to the DualSense controller integration.
"""

import threading
import time
from typing import Any

# Try to import SDL2 dependencies, but allow fallback if not available
try:
    import sdl2
    import sdl2.ext

    SDL2_AVAILABLE = True
except ImportError:
    SDL2_AVAILABLE = False

from src.common.logging.logger_api import Logger


class DualSenseFeedback:
    """Class to add rumble and LED functionality to DualSense controller."""

    def __init__(self, dualsense_feedback_logger: Logger):
        """Initialize the DualSense feedback controller."""
        self.logger = dualsense_feedback_logger
        self.logger.infow("Initializing DualSense feedback controller")

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
            self.logger.warnw("SDL2 not available, DualSense feedback features will be disabled")

    def _initialize_sdl(self):
        """Initialize SDL2 for DualSense feedback features."""
        try:
            # Initialize SDL2 with required subsystems
            if sdl2.SDL_Init(sdl2.SDL_INIT_GAMECONTROLLER | sdl2.SDL_INIT_HAPTIC) != 0:
                error = sdl2.SDL_GetError().decode("utf-8")
                self.logger.errorw("SDL2 initialization error", "error", error)
                return False

            # Look for DualSense controller
            num_joysticks = sdl2.SDL_NumJoysticks()
            if num_joysticks == 0:
                self.logger.warnw("No controllers detected for SDL2")
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
                        self.logger.infow(
                            f"SDL2 initialized for DualSense feedback", "controller_name", name
                        )
                        return True
                    else:
                        # Close if not a DualSense
                        sdl2.SDL_GameControllerClose(temp_controller)
                except Exception as e:
                    self.logger.errorw("Error determining controller name", "error", str(e))
                    sdl2.SDL_GameControllerClose(temp_controller)

            self.logger.warnw("No DualSense controller found for SDL2")
            sdl2.SDL_Quit()
            return False

        except Exception as e:
            self.logger.errorw("Error initializing SDL2", "error", str(e))
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
            self.logger.warnw("LED control not supported in this SDL2 version")
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
            self.logger.warnw("Rumble not supported")
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
            self.logger.errorw("Error setting haptic rumble", "error", str(e))
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
