"""This module contains the LedAnimationThread class, which is responsible for controlling the LED animations on the robot."""

import threading
import time


class AnimationType:
    HIT = "HIT"
    CAPTURING = "CAPTURING"
    SCORED = "SCORED"
    FLAG_POSSESSED = "FLAG_POSSESSED"
    TEAM_COLOR = "TEAM_COLOR"
    OFF = "OFF"


class LedAnimationThread(threading.Thread):
    def __init__(self, color_setter, team_color):
        super().__init__()
        self.color_setter = color_setter
        self.team_color = team_color
        self.current_animation = AnimationType.TEAM_COLOR
        self.animation_duration = 0
        self.animation_end_time = time.time()
        self.running = True
        self.lock = threading.Lock()

    def run(self):
        while self.running:
            now = time.time()
            with self.lock:
                if now > self.animation_end_time:
                    self.current_animation = AnimationType.TEAM_COLOR

                self.execute_current_animation()

            if self.current_animation in [AnimationType.CAPTURING, AnimationType.FLAG_POSSESSED]:
                time.sleep(0.01)  # Fast loop for continuous animations
            else:
                time.sleep(0.05)  # Slower loop for intermittent animations

    def set_animation(self, animation_type, duration):
        with self.lock:
            self.current_animation = animation_type
            self.animation_duration = duration
            self.animation_end_time = time.time() + duration

    def stop_animation(self):
        with self.lock:
            # Force current animation to expire immediately
            self.animation_end_time = time.time() - 1  # Ensures immediate stop

    def execute_current_animation(self):
        # Implement your actual animation patterns here
        if self.current_animation == AnimationType.CAPTURING:
            for brightness in range(0, 101, 5):
                intensity = int(255 * brightness / 100)
                self.color_setter((0, 0, intensity))
                time.sleep(0.05)
            for brightness in range(100, -1, -5):
                intensity = int(255 * brightness / 100)
                self.color_setter((0, 0, intensity))
                time.sleep(0.05)
        elif self.current_animation == AnimationType.FLAG_POSSESSED:
            self.color_setter((255, 0, 0))  # Purple
        elif self.current_animation == AnimationType.HIT:
            self.color_setter((255, 165, 0))  # Orange
            time.sleep(0.2)
            self.color_setter((0, 0, 0))  # Off
            time.sleep(0.2)
        elif self.current_animation == AnimationType.SCORED:
            self.color_setter((0, 255, 0))  # Green
            time.sleep(0.3)
            self.color_setter((0, 0, 0))  # Off
            time.sleep(0.3)
        elif self.current_animation == AnimationType.TEAM_COLOR:
            self.color_setter(self.team_color)

    def stop(self):
        self.running = False
