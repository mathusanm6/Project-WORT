"""This module contains the LedAnimationThread class, which is responsible for controlling the LED animations on the robot."""

import queue
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
    def __init__(self, set_color_func, team_color):
        super().__init__(daemon=True)
        self.set_color = set_color_func
        self.team_color = team_color
        self.animation_queue = queue.Queue()
        self.active = True
        self.current_animation = None

    def run(self):
        while self.active:
            try:
                animation, duration = self.animation_queue.get(timeout=0.1)
                self.current_animation = animation

                if animation == AnimationType.HIT:
                    end_time = time.time() + duration
                    while time.time() < end_time:
                        self.set_color((255, 165, 0))  # Orange
                        time.sleep(0.2)
                        self.set_color((0, 0, 0))  # Off
                        time.sleep(0.2)

                elif animation == AnimationType.CAPTURING:
                    while self.current_animation == AnimationType.CAPTURING:
                        for brightness in range(0, 101, 5):
                            intensity = int(255 * brightness / 100)
                            self.set_color((0, 0, intensity))
                            time.sleep(0.05)
                        for brightness in range(100, -1, -5):
                            intensity = int(255 * brightness / 100)
                            self.set_color((0, 0, intensity))
                            time.sleep(0.05)

                elif animation == AnimationType.SCORED:
                    end_time = time.time() + duration
                    while time.time() < end_time:
                        self.set_color((0, 255, 0))  # Green
                        time.sleep(0.3)
                        self.set_color((0, 0, 0))  # Off
                        time.sleep(0.3)

                elif animation == AnimationType.FLAG_POSSESSED:
                    self.set_color((128, 0, 128))  # Purple
                    time.sleep(duration)

                self.set_color(self.team_color)
                self.animation_queue.task_done()

            except queue.Empty:
                continue

    def stop(self):
        self.active = False

    def set_animation(self, animation, duration=2):
        self.animation_queue.put((animation, duration))
