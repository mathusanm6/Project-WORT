"""This module provides a class for controlling the LED strip on the Rasptank."""

import logging
import threading
import time
from enum import Enum

import RPi.GPIO as GPIO
from rpi_ws281x import Adafruit_NeoPixel, Color

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

    def __init__(self):
        """Initialize the LED strip."""
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
        self.animation_thread = LedAnimationThread(self.set_color, self.team_color)
        self.animation_thread.start()

    def set_color(self, color):
        """Set all LEDs to the same color."""
        try:
            # Extract RGB components
            r, g, b = color

            # Set each pixel's color
            for i in range(self.strip.numPixels()):
                self.strip.setPixelColor(i, Color(r, g, b))

            # Update the strip
            self.strip.show()
        except Exception as e:
            logging.error(f"Error setting LED color: {e}")

    def set_team(self, team):
        """Set the team color and persist it as the default state."""
        if team.lower() == "blue":
            self.team_color = self.COLOR_BLUE
            self.current_state = LedStripState.TEAM_BLUE
            self.set_color(self.COLOR_BLUE)
        elif team.lower() == "red":
            self.team_color = self.COLOR_RED
            self.current_state = LedStripState.TEAM_RED
            self.set_color(self.COLOR_RED)
        else:
            logging.warning(f"Unknown team color: {team}. Using blue as default.")
            self.team_color = self.COLOR_BLUE
            self.current_state = LedStripState.TEAM_BLUE
            self.set_color(self.COLOR_BLUE)

    def hit_animation(self, duration=2.0):
        self.strip.begin()
        self.animation_thread.set_animation(AnimationType.HIT, duration)

    def capturing_animation(self):
        self.strip.begin()
        self.animation_thread.set_animation(
            AnimationType.CAPTURING, duration=9999
        )  # Infinite until stopped explicitly

    def scored_animation(self, duration=3.0):
        self.strip.begin()
        self.animation_thread.set_animation(AnimationType.SCORED, duration)

    def flag_possessed(self, duration=9999):
        self.strip.begin()
        self.animation_thread.set_animation(AnimationType.FLAG_POSSESSED, duration)

    def reset_to_team_color(self):
        self.strip.begin()
        self.animation_thread.set_animation(AnimationType.TEAM_COLOR, duration=0.1)

    def stop_animations(self):
        self.strip.begin()

        # Resetting to team color stops any long-running animation (like capturing)
        self.reset_to_team_color()

    def turn_off(self):
        self.strip.begin()
        self.animation_thread.set_animation(AnimationType.OFF, duration=0.1)

    def cleanup(self):
        """Clean up resources before exiting."""

        self.turn_off()
        time.sleep(0.1)

        self.animation_thread.stop()
        self.animation_thread.join(timeout=1)

        logging.info("LED strip cleanup complete")
