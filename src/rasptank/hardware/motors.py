"""This module provides a class to control the motors of the Rasptank robot."""

import logging
import time
from enum import Enum

import RPi.GPIO as GPIO


class Direction(Enum):
    """Direction of motor movement."""

    FORWARD = 0
    BACKWARD = 1


class MotorPins(Enum):
    """GPIO pins for motors."""

    MOTOR_A_EN = 4
    MOTOR_B_EN = 17
    MOTOR_A_PIN1 = 14
    MOTOR_A_PIN2 = 15
    MOTOR_B_PIN1 = 27
    MOTOR_B_PIN2 = 18


class RasptankMotors:
    # Kickstart constants
    KICKSTART_THRESHOLD = 20
    KICKSTART_DUTY_CYCLE = 50
    KICKSTART_DURATION = 0.1

    def __init__(self):
        """Initialize GPIO and motor controllers"""
        self.pwm_A = None
        self.pwm_B = None
        self._setup()

    def _setup(self):
        """Set up GPIO pins and PWM for motors."""
        # Set up motor pins
        GPIO.setup(MotorPins.MOTOR_A_EN.value, GPIO.OUT)
        GPIO.setup(MotorPins.MOTOR_B_EN.value, GPIO.OUT)
        GPIO.setup(MotorPins.MOTOR_A_PIN1.value, GPIO.OUT)
        GPIO.setup(MotorPins.MOTOR_A_PIN2.value, GPIO.OUT)
        GPIO.setup(MotorPins.MOTOR_B_PIN1.value, GPIO.OUT)
        GPIO.setup(MotorPins.MOTOR_B_PIN2.value, GPIO.OUT)

        # Initialize PWM
        try:
            self.pwm_A = GPIO.PWM(MotorPins.MOTOR_A_EN.value, 1000)
            self.pwm_B = GPIO.PWM(MotorPins.MOTOR_B_EN.value, 1000)
            # Start PWM with 0 duty cycle (motors off)
            self.pwm_A.start(0)
            self.pwm_B.start(0)
        except Exception as e:
            print(f"PWM setup error: {e}")

        # Stop motors initially
        self.motor_stop()

    def motor_stop(self):
        """Stop all motors"""
        GPIO.output(MotorPins.MOTOR_A_PIN1.value, GPIO.LOW)
        GPIO.output(MotorPins.MOTOR_A_PIN2.value, GPIO.LOW)
        GPIO.output(MotorPins.MOTOR_B_PIN1.value, GPIO.LOW)
        GPIO.output(MotorPins.MOTOR_B_PIN2.value, GPIO.LOW)
        # Set duty cycle to 0 to stop motors
        self.pwm_A.ChangeDutyCycle(0)
        self.pwm_B.ChangeDutyCycle(0)

    def motor_left(self, status, direction, speed_value):
        """Control left motor"""
        if status == 0:  # stop
            GPIO.output(MotorPins.MOTOR_B_PIN1.value, GPIO.LOW)
            GPIO.output(MotorPins.MOTOR_B_PIN2.value, GPIO.LOW)
            self.pwm_B.ChangeDutyCycle(0)
        else:
            if direction == Direction.BACKWARD:
                GPIO.output(MotorPins.MOTOR_B_PIN1.value, GPIO.LOW)
                GPIO.output(MotorPins.MOTOR_B_PIN2.value, GPIO.HIGH)
            elif direction == Direction.FORWARD:
                GPIO.output(MotorPins.MOTOR_B_PIN1.value, GPIO.HIGH)
                GPIO.output(MotorPins.MOTOR_B_PIN2.value, GPIO.LOW)
            if speed_value < self.KICKSTART_THRESHOLD:
                self.pwm_B.ChangeDutyCycle(self.KICKSTART_DUTY_CYCLE)
                time.sleep(self.KICKSTART_DURATION)
            self.pwm_B.ChangeDutyCycle(int(speed_value))

    def motor_right(self, status, direction, speed_value):
        """Control right motor"""
        if status == 0:  # stop
            GPIO.output(MotorPins.MOTOR_A_PIN1.value, GPIO.LOW)
            GPIO.output(MotorPins.MOTOR_A_PIN2.value, GPIO.LOW)
            self.pwm_A.ChangeDutyCycle(0)
        else:
            if direction == Direction.FORWARD:
                GPIO.output(MotorPins.MOTOR_A_PIN1.value, GPIO.LOW)
                GPIO.output(MotorPins.MOTOR_A_PIN2.value, GPIO.HIGH)
            elif direction == Direction.BACKWARD:
                GPIO.output(MotorPins.MOTOR_A_PIN1.value, GPIO.HIGH)
                GPIO.output(MotorPins.MOTOR_A_PIN2.value, GPIO.LOW)
            if speed_value < self.KICKSTART_THRESHOLD:
                self.pwm_A.ChangeDutyCycle(self.KICKSTART_DUTY_CYCLE)
                time.sleep(self.KICKSTART_DURATION)
            self.pwm_A.ChangeDutyCycle(int(speed_value))

    def cleanup(self):
        """Clean up GPIO and threads."""
        # Stop motors first
        self.motor_stop()

        # Stop PWM safely
        if self.pwm_A:
            self.pwm_A.stop()
        if self.pwm_B:
            self.pwm_B.stop()
        logging.info("Motors stopped")
