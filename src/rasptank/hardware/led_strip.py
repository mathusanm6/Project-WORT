"""This module provides a class for controlling the LED strip on the Rasptank."""

from enum import Enum

from RPi import GPIO
from rpi_ws281x import Adafruit_NeoPixel, Color

from src.common.logging.logger_factory import LoggerFactory
from src.rasptank.hardware.led_animations import AnimationType, LedAnimationThread


class LedStripState(Enum):
    """Enum representing different LED strip states."""

    IDLE = 0
    HIT = 1
    CAPTURING = 2
    FLAG_POSSESSED = 3
    SCORED = 4
    TEAM_BLUE = 5
    TEAM_RED = 6


class RasptankLedStrip:
    """Class for controlling the LED strip on the Rasptank."""

    def __init__(self, led_strip_logger: LoggerFactory):
        """Initialize the LED strip."""
        # Create logger
        self.logger = led_strip_logger
        self.logger.infow("Initializing Rasptank LED strip")

        # LED strip configuration
        self.LED_COUNT = 12  # Number of LED pixels
        self.LED_PIN = 12  # GPIO pin connected to the pixels
        self.LED_FREQ_HZ = 800000  # LED signal frequency in hertz
        self.LED_DMA = 10  # DMA channel to use for generating signal
        self.LED_BRIGHTNESS = 255  # 0-255
        self.LED_INVERT = False  # True to invert the signal
        self.LED_CHANNEL = 0  # set to '1' for GPIOs 13, 19, 41, 45 or 53

        # Define colors (R, G, B)
        self.COLOR_RED = (255, 0, 0)
        self.COLOR_BLUE = (0, 0, 255)
        self.COLOR_GREEN = (0, 255, 0)
        self.COLOR_ORANGE = (255, 165, 0)
        self.COLOR_PURPLE = (128, 0, 128)
        self.COLOR_OFF = (0, 0, 0)

        # State tracking
        self.current_state = LedStripState.TEAM_BLUE
        self.team_color = self.COLOR_BLUE  # Default team

        # Initialize the strip
        self.logger.debugw(
            "Creating NeoPixel instance",
            "led_count",
            self.LED_COUNT,
            "led_pin",
            self.LED_PIN,
            "led_freq",
            self.LED_FREQ_HZ,
        )

        self.strip = Adafruit_NeoPixel(
            self.LED_COUNT,
            self.LED_PIN,
            self.LED_FREQ_HZ,
            self.LED_DMA,
            self.LED_INVERT,
            self.LED_BRIGHTNESS,
            self.LED_CHANNEL,
        )
        self.strip.begin()

        # Turn off all LEDs initially
        self.set_color(self.COLOR_BLUE)

        # Start the animation thread
        self.logger.debugw("Starting LED animation thread")
        self.animation_thread = LedAnimationThread(self.set_color, self.team_color)
        self.animation_thread.start()

        self.logger.infow("LED strip initialized")

    def set_color(self, color):
        """Set all LEDs to the same color."""
        try:
            # Extract RGB components
            r, g, b = color

            self.logger.debugw("Setting LED color", "r", r, "g", g, "b", b)

            # Set each pixel's color
            for i in range(self.strip.numPixels()):
                self.strip.setPixelColor(i, Color(r, g, b))

            # Update the strip
            self.strip.show()
        except Exception as e:
            self.logger.errorw("Error setting LED color", "error", str(e), exc_info=True)

    def set_team(self, team):
        """Set the team color and persist it as the default state."""
        self.logger.infow("Setting team color", "team", team)

        if team.lower() == "blue":
            self.team_color = self.COLOR_BLUE
            self.current_state = LedStripState.TEAM_BLUE
            self.set_color(self.COLOR_BLUE)
        elif team.lower() == "red":
            self.team_color = self.COLOR_RED
            self.current_state = LedStripState.TEAM_RED
            self.set_color(self.COLOR_RED)
        else:
            self.logger.warnw("Unknown team color, using blue as default", "team", team)
            self.team_color = self.COLOR_BLUE
            self.current_state = LedStripState.TEAM_BLUE
            self.set_color(self.COLOR_BLUE)

    def hit_animation(self, duration=2.0):
        """Play the hit animation."""
        self.logger.debugw("Starting hit animation", "duration", duration)
        self.strip.begin()
        self.current_state = LedStripState.HIT
        self.animation_thread.set_animation(AnimationType.HIT, duration)

    def capturing_animation(self):
        """Play the capturing animation."""
        self.logger.debugw("Starting capturing animation")
        self.strip.begin()
        self.current_state = LedStripState.CAPTURING
        self.animation_thread.set_animation(
            AnimationType.CAPTURING, duration=9999
        )  # Infinite until stopped explicitly

    def scored_animation(self, duration=3.0):
        """Play the scored animation."""
        self.logger.debugw("Starting scored animation", "duration", duration)
        self.strip.begin()
        self.current_state = LedStripState.SCORED
        self.animation_thread.set_animation(AnimationType.SCORED, duration)

    def flag_possessed(self, duration=9999):
        """Play the flag possessed animation."""
        self.logger.debugw("Starting flag possessed animation", "duration", duration)
        self.strip.begin()
        self.current_state = LedStripState.FLAG_POSSESSED
        self.animation_thread.set_animation(AnimationType.FLAG_POSSESSED, duration)

    def stop_animations(self):
        """Stop all animations and return to team color."""
        self.logger.debugw("Stopping animations")
        self.strip.begin()
        self.current_state = self.team_color
        self.animation_thread.stop_animation()
        self.set_color(self.team_color)

    def turn_off(self):
        """Turn off all LEDs."""
        self.logger.debugw("Turning off all LEDs")
        self.strip.begin()
        self.current_state = LedStripState.IDLE
        self.set_color(self.COLOR_OFF)

    def cleanup(self):
        """Clean up resources before exiting."""
        self.logger.infow("Cleaning up LED strip resources")

        try:
            self.animation_thread.stop()
            self.animation_thread.join(timeout=1)
            self.logger.debugw("Animation thread stopped")
        except Exception as e:
            self.logger.errorw("Error stopping animation thread", "error", str(e), exc_info=True)

        try:
            self.turn_off()
            self.logger.debugw("LEDs turned off")
        except Exception as e:
            self.logger.errorw("Error turning off LEDs", "error", str(e), exc_info=True)

        self.logger.infow("LED strip cleanup complete")
