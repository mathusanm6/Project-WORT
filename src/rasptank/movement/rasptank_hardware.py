"""Hardware-specific implementation for Rasptank motors"""

import time
from enum import Enum

import RPi.GPIO as GPIO

from src.rasptank.movement.movement_api import ThrustDirection, TurnDirection


class TurnFactor(Enum):
    """Turning factor for the Rasptank movement controller"""

    NONE = 0.0
    MODERATE = 0.6
    SHARP = 1.0


class RasptankHardware:
    """Hardware-specific implementation for Rasptank motors"""

    # GPIO pin definitions
    Motor_A_EN = 4
    Motor_B_EN = 17
    Motor_A_Pin1 = 14
    Motor_A_Pin2 = 15
    Motor_B_Pin1 = 27
    Motor_B_Pin2 = 18

    # Direction constants
    Dir_forward = 0
    Dir_backward = 1
    left_forward = 0
    left_backward = 1
    right_forward = 0
    right_backward = 1

    def __init__(self):
        """Initialize GPIO and motor controllers"""
        self.pwm_A = None
        self.pwm_B = None
        self._setup()

    def _setup(self):
        """Set up GPIO pins and PWM"""
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)

        # Set up motor pins
        GPIO.setup(self.Motor_A_EN, GPIO.OUT)
        GPIO.setup(self.Motor_B_EN, GPIO.OUT)
        GPIO.setup(self.Motor_A_Pin1, GPIO.OUT)
        GPIO.setup(self.Motor_A_Pin2, GPIO.OUT)
        GPIO.setup(self.Motor_B_Pin1, GPIO.OUT)
        GPIO.setup(self.Motor_B_Pin2, GPIO.OUT)

        # Stop motors initially
        self._motor_stop()

        # Set up PWM
        try:
            self.pwm_A = GPIO.PWM(self.Motor_A_EN, 1000)
            self.pwm_B = GPIO.PWM(self.Motor_B_EN, 1000)
        except Exception as e:
            print(f"PWM setup error: {e}")

    def _motor_stop(self):
        """Stop all motors"""
        GPIO.output(self.Motor_A_Pin1, GPIO.LOW)
        GPIO.output(self.Motor_A_Pin2, GPIO.LOW)
        GPIO.output(self.Motor_B_Pin1, GPIO.LOW)
        GPIO.output(self.Motor_B_Pin2, GPIO.LOW)
        GPIO.output(self.Motor_A_EN, GPIO.LOW)
        GPIO.output(self.Motor_B_EN, GPIO.LOW)

    def _motor_left(self, status, direction, speed):
        """Control left motor"""
        if status == 0:  # stop
            GPIO.output(self.Motor_B_Pin1, GPIO.LOW)
            GPIO.output(self.Motor_B_Pin2, GPIO.LOW)
            GPIO.output(self.Motor_B_EN, GPIO.LOW)
        else:
            if direction == self.Dir_backward:
                GPIO.output(self.Motor_B_Pin1, GPIO.HIGH)
                GPIO.output(self.Motor_B_Pin2, GPIO.LOW)
                self.pwm_B.start(100)
                self.pwm_B.ChangeDutyCycle(speed)
            elif direction == self.Dir_forward:
                GPIO.output(self.Motor_B_Pin1, GPIO.LOW)
                GPIO.output(self.Motor_B_Pin2, GPIO.HIGH)
                self.pwm_B.start(0)
                self.pwm_B.ChangeDutyCycle(speed)

    def _motor_right(self, status, direction, speed):
        """Control right motor"""
        if status == 0:  # stop
            GPIO.output(self.Motor_A_Pin1, GPIO.LOW)
            GPIO.output(self.Motor_A_Pin2, GPIO.LOW)
            GPIO.output(self.Motor_A_EN, GPIO.LOW)
        else:
            if direction == self.Dir_forward:
                GPIO.output(self.Motor_A_Pin1, GPIO.HIGH)
                GPIO.output(self.Motor_A_Pin2, GPIO.LOW)
                self.pwm_A.start(100)
                self.pwm_A.ChangeDutyCycle(speed)
            elif direction == self.Dir_backward:
                GPIO.output(self.Motor_A_Pin1, GPIO.LOW)
                self.pwm_A.start(0)
                GPIO.output(self.Motor_A_Pin2, GPIO.HIGH)
                self.pwm_A.ChangeDutyCycle(speed)

    def move_hardware(
        self,
        thrust_direction: ThrustDirection,
        turn_direction: TurnDirection,
        speed: float,
        turn_factor: float,
    ):
        """Direct hardware movement implementation.

        Args:
            thrust_direction (ThrustDirection): Thrust direction
            turn_direction (TurnDirection): Turn direction
            speed (float): Speed factor between 0.0 and 100.0
            turn_factor (float): Turning factor between 0.0 and 1.0 (affects the sharpness of the turn)
        """
        if thrust_direction == ThrustDirection.FORWARD:
            if turn_direction == TurnDirection.LEFT:
                self._motor_left(1, self.left_forward, int(speed * turn_factor))
                self._motor_right(1, self.right_backward, speed)
            elif turn_direction == TurnDirection.RIGHT:
                self._motor_left(1, self.left_backward, speed)
                self._motor_right(1, self.right_forward, int(speed * turn_factor))
            else:
                self._motor_left(1, self.left_backward, speed)
                self._motor_right(1, self.right_backward, speed)
        elif thrust_direction == ThrustDirection.BACKWARD:
            if turn_direction == TurnDirection.LEFT:
                self._motor_left(1, self.left_backward, int(speed * turn_factor))
                self._motor_right(1, self.right_forward, speed)
            elif turn_direction == TurnDirection.RIGHT:
                self._motor_left(1, self.left_forward, speed)
                self._motor_right(1, self.right_backward, int(speed * turn_factor))
            else:
                self._motor_left(1, self.left_forward, speed)
                self._motor_right(1, self.right_forward, speed)
        elif thrust_direction == ThrustDirection.NONE:
            if turn_direction == TurnDirection.RIGHT:
                self._motor_left(1, self.left_backward, speed)
                self._motor_right(1, self.right_forward, speed)
            elif turn_direction == TurnDirection.LEFT:
                self._motor_left(1, self.left_forward, speed)
                self._motor_right(1, self.right_backward, speed)
            else:
                self._motor_stop()

    def cleanup(self):
        """Clean up GPIO resources"""
        self._motor_stop()
        GPIO.cleanup()
