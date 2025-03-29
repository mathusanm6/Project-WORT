"""This module provides a class to control the motors of the Rasptank robot."""

import time
from enum import Enum

from RPi import GPIO

from src.common.logging.decorators import log_function_call
from src.common.logging.logger_api import Logger


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
    """Class to control the Rasptank's motors."""

    # Kickstart constants
    KICKSTART_THRESHOLD = 20
    KICKSTART_DUTY_CYCLE = 50
    KICKSTART_DURATION = 0.1

    def __init__(self, motor_logger: Logger):
        """Initialize GPIO and motor controllers"""
        # Create logger
        self.logger = motor_logger
        self.logger.debugw("Initializing motors controller")

        self.pwm_A = None
        self.pwm_B = None
        self._setup()

        self.logger.infow("Motors controller initialized")

    def _setup(self):
        """Set up GPIO pins and PWM for motors."""
        # Set up motor pins
        self.logger.debugw("Setting up motor GPIO pins")

        GPIO.setup(MotorPins.MOTOR_A_EN.value, GPIO.OUT)
        GPIO.setup(MotorPins.MOTOR_B_EN.value, GPIO.OUT)
        GPIO.setup(MotorPins.MOTOR_A_PIN1.value, GPIO.OUT)
        GPIO.setup(MotorPins.MOTOR_A_PIN2.value, GPIO.OUT)
        GPIO.setup(MotorPins.MOTOR_B_PIN1.value, GPIO.OUT)
        GPIO.setup(MotorPins.MOTOR_B_PIN2.value, GPIO.OUT)

        # Initialize PWM
        try:
            self.logger.debugw(
                "Initializing PWM",
                "freq",
                1000,
                "pin_A",
                MotorPins.MOTOR_A_EN.value,
                "pin_B",
                MotorPins.MOTOR_B_EN.value,
            )

            self.pwm_A = GPIO.PWM(MotorPins.MOTOR_A_EN.value, 1000)
            self.pwm_B = GPIO.PWM(MotorPins.MOTOR_B_EN.value, 1000)

            if not self.pwm_A or not self.pwm_B:
                raise RuntimeError("PWM failed to initialize")

            # Start PWM with 0 duty cycle (motors off)
            self.pwm_A.start(0)
            self.pwm_B.start(0)

            self.logger.debugw("PWM initialized successfully")
        except Exception as e:
            self.logger.errorw("PWM setup error", "error", str(e), exc_info=True)

        # Stop motors initially
        self.motor_stop()

    def motor_stop(self):
        """Stop all motors"""
        self.logger.debugw("Stopping all motors")

        GPIO.output(MotorPins.MOTOR_A_PIN1.value, GPIO.LOW)
        GPIO.output(MotorPins.MOTOR_A_PIN2.value, GPIO.LOW)
        GPIO.output(MotorPins.MOTOR_B_PIN1.value, GPIO.LOW)
        GPIO.output(MotorPins.MOTOR_B_PIN2.value, GPIO.LOW)

        # Set duty cycle to 0 to stop motors
        self.pwm_A.ChangeDutyCycle(0)
        self.pwm_B.ChangeDutyCycle(0)

    def motor_left(self, status, direction, speed_value):
        """Control left motor

        Args:
            status (int): 0 to stop, 1 to move
            direction (Direction): FORWARD or BACKWARD
            speed_value (int): Motor speed (0-100)
        """
        self.logger.debugw(
            "Left motor control",
            "status",
            status,
            "direction",
            direction.name if isinstance(direction, Direction) else direction,
            "speed",
            speed_value,
        )

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
                self.logger.debugw(
                    "Applying left motor kickstart",
                    "kickstart_duty",
                    self.KICKSTART_DUTY_CYCLE,
                    "duration",
                    self.KICKSTART_DURATION,
                )
                self.pwm_B.ChangeDutyCycle(self.KICKSTART_DUTY_CYCLE)
                time.sleep(self.KICKSTART_DURATION)

            self.pwm_B.ChangeDutyCycle(int(speed_value))

    def motor_right(self, status, direction, speed_value):
        """Control right motor

        Args:
            status (int): 0 to stop, 1 to move
            direction (Direction): FORWARD or BACKWARD
            speed_value (int): Motor speed (0-100)
        """
        self.logger.debugw(
            "Right motor control",
            "status",
            status,
            "direction",
            direction.name if isinstance(direction, Direction) else direction,
            "speed",
            speed_value,
        )

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
                self.logger.debugw(
                    "Applying right motor kickstart",
                    "kickstart_duty",
                    self.KICKSTART_DUTY_CYCLE,
                    "duration",
                    self.KICKSTART_DURATION,
                )
                self.pwm_A.ChangeDutyCycle(self.KICKSTART_DUTY_CYCLE)
                time.sleep(self.KICKSTART_DURATION)

            self.pwm_A.ChangeDutyCycle(int(speed_value))

    @log_function_call()
    def cleanup(self):
        """Clean up GPIO and threads."""
        self.logger.infow("Cleaning up motors")

        # Stop motors first
        try:
            self.motor_stop()
            self.logger.debugw("Motors stopped")
        except Exception as e:
            self.logger.errorw("Error stopping motors", "error", str(e), exc_info=True)

        # Stop PWM safely
        try:
            if self.pwm_A:
                self.pwm_A.stop()
                self.logger.debugw("PWM A stopped")
                del self.pwm_A
                self.logger.debugw("PWM A deleted")
            if self.pwm_B:
                self.pwm_B.stop()
                self.logger.debugw("PWM B stopped")
                del self.pwm_B
                self.logger.debugw("PWM B deleted")
        except Exception as e:
            self.logger.errorw("Error stopping PWM", "error", str(e), exc_info=True)

        self.logger.infow("Motors cleanup complete")
