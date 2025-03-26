"""Hardware-specific implementation for Rasptank motors"""

import time

import RPi.GPIO as GPIO

# Import from src.common
from src.common.enum.movement import (
    CurvedTurnRate,
    SpeedMode,
    ThrustDirection,
    TurnDirection,
    TurnType,
)


class RasptankHardware:
    """Hardware-specific implementation for Rasptank motors"""

    # GPIO pin definitions
    MOTOR_A_EN = 4
    MOTOR_B_EN = 17
    MOTOR_A_PIN1 = 14
    MOTOR_A_PIN2 = 15
    MOTOR_B_PIN1 = 27
    MOTOR_B_PIN2 = 18

    # Direction constants
    DIR_FORWARD = 0
    DIR_BACKWARD = 1

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
        """Set up GPIO pins and PWM"""
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)

        # Set up motor pins
        GPIO.setup(self.MOTOR_A_EN, GPIO.OUT)
        GPIO.setup(self.MOTOR_B_EN, GPIO.OUT)
        GPIO.setup(self.MOTOR_A_PIN1, GPIO.OUT)
        GPIO.setup(self.MOTOR_A_PIN2, GPIO.OUT)
        GPIO.setup(self.MOTOR_B_PIN1, GPIO.OUT)
        GPIO.setup(self.MOTOR_B_PIN2, GPIO.OUT)

        # Initialize PWM
        try:
            self.pwm_A = GPIO.PWM(self.MOTOR_A_EN, 1000)
            self.pwm_B = GPIO.PWM(self.MOTOR_B_EN, 1000)
            # Start PWM with 0 duty cycle (motors off)
            self.pwm_A.start(0)
            self.pwm_B.start(0)
        except Exception as e:
            print(f"PWM setup error: {e}")

        # Stop motors initially
        self._motor_stop()

    def _motor_stop(self):
        """Stop all motors"""
        GPIO.output(self.MOTOR_A_PIN1, GPIO.LOW)
        GPIO.output(self.MOTOR_A_PIN2, GPIO.LOW)
        GPIO.output(self.MOTOR_B_PIN1, GPIO.LOW)
        GPIO.output(self.MOTOR_B_PIN2, GPIO.LOW)
        # Set duty cycle to 0 to stop motors
        self.pwm_A.ChangeDutyCycle(0)
        self.pwm_B.ChangeDutyCycle(0)

    def _motor_left(self, status, direction, speed_value):
        """Control left motor"""
        if status == 0:  # stop
            GPIO.output(self.MOTOR_B_PIN1, GPIO.LOW)
            GPIO.output(self.MOTOR_B_PIN2, GPIO.LOW)
            self.pwm_B.ChangeDutyCycle(0)
        else:
            if direction == self.DIR_BACKWARD:
                GPIO.output(self.MOTOR_B_PIN1, GPIO.LOW)
                GPIO.output(self.MOTOR_B_PIN2, GPIO.HIGH)
            elif direction == self.DIR_FORWARD:
                GPIO.output(self.MOTOR_B_PIN1, GPIO.HIGH)
                GPIO.output(self.MOTOR_B_PIN2, GPIO.LOW)
            if speed_value < self.KICKSTART_THRESHOLD:
                self.pwm_B.ChangeDutyCycle(self.KICKSTART_DUTY_CYCLE)
                time.sleep(self.KICKSTART_DURATION)
            self.pwm_B.ChangeDutyCycle(int(speed_value))

    def _motor_right(self, status, direction, speed_value):
        """Control right motor"""
        if status == 0:  # stop
            GPIO.output(self.MOTOR_A_PIN1, GPIO.LOW)
            GPIO.output(self.MOTOR_A_PIN2, GPIO.LOW)
            self.pwm_A.ChangeDutyCycle(0)
        else:
            if direction == self.DIR_FORWARD:
                GPIO.output(self.MOTOR_A_PIN1, GPIO.LOW)
                GPIO.output(self.MOTOR_A_PIN2, GPIO.HIGH)
            elif direction == self.DIR_BACKWARD:
                GPIO.output(self.MOTOR_A_PIN1, GPIO.HIGH)
                GPIO.output(self.MOTOR_A_PIN2, GPIO.LOW)
            if speed_value < self.KICKSTART_THRESHOLD:
                self.pwm_A.ChangeDutyCycle(self.KICKSTART_DUTY_CYCLE)
                time.sleep(self.KICKSTART_DURATION)
            self.pwm_A.ChangeDutyCycle(int(speed_value))

    def move_hardware(
        self,
        thrust_direction: ThrustDirection,
        turn_direction: TurnDirection,
        turn_type: TurnType,
        speed_mode: SpeedMode,
        curved_turn_rate: CurvedTurnRate,
    ):
        """Direct hardware movement implementation.

        Args:
            thrust_direction (ThrustDirection): FORWARD/BACKWARD/NONE
            turn_direction (TurnDirection): LEFT/RIGHT/NONE
            turn_type (TurnType): SPIN/PIVOT/CURVE/NONE
            speed_mode (SpeedMode): STOP/GEAR_1/GEAR_2/GEAR_3
            curved_turn_rate (CurvedTurnRate): Rate of turn for CURVE turn type (0.0 to 1.0 with 0.0 being no curve)
        """
        speed_value = speed_mode.value
        curved_turn_rate_value = curved_turn_rate.value

        # Forward movement handling
        if thrust_direction == ThrustDirection.FORWARD:
            if turn_direction == TurnDirection.NONE:
                self._motor_left(1, self.DIR_FORWARD, speed_value)
                self._motor_right(1, self.DIR_FORWARD, speed_value)
            elif turn_direction == TurnDirection.LEFT:
                if turn_type == TurnType.CURVE:
                    self._motor_left(
                        1, self.DIR_FORWARD, int(speed_value * (1 - curved_turn_rate_value))
                    )
                    self._motor_right(1, self.DIR_FORWARD, speed_value)
                else:
                    raise ValueError("Turn type must be CURVE for FORWARD + LEFT")
            elif turn_direction == TurnDirection.RIGHT:
                if turn_type == TurnType.CURVE:
                    self._motor_left(1, self.DIR_FORWARD, speed_value)
                    self._motor_right(
                        1, self.DIR_FORWARD, int(speed_value * (1 - curved_turn_rate_value))
                    )
                else:
                    raise ValueError("Turn type must be CURVE for FORWARD + RIGHT")
            else:
                raise ValueError("Invalid turn direction")
            return

        # Backward movement handling
        if thrust_direction == ThrustDirection.BACKWARD:
            if turn_direction == TurnDirection.NONE:
                self._motor_left(1, self.DIR_BACKWARD, speed_value)
                self._motor_right(1, self.DIR_BACKWARD, speed_value)
            elif turn_direction == TurnDirection.LEFT:
                if turn_type == TurnType.CURVE:
                    self._motor_left(
                        1, self.DIR_BACKWARD, int(speed_value * (1 - curved_turn_rate_value))
                    )
                    self._motor_right(1, self.DIR_BACKWARD, speed_value)
                else:
                    raise ValueError("Turn type must be CURVE for BACKWARD + LEFT")
            elif turn_direction == TurnDirection.RIGHT:
                if turn_type == TurnType.CURVE:
                    self._motor_left(1, self.DIR_BACKWARD, speed_value)
                    self._motor_right(
                        1, self.DIR_BACKWARD, int(speed_value * (1 - curved_turn_rate_value))
                    )
                else:
                    raise ValueError("Turn type must be CURVE for BACKWARD + RIGHT")
            else:
                raise ValueError("Invalid turn direction")
            return

        # No thrust (stationary) handling
        if thrust_direction == ThrustDirection.NONE:
            if turn_direction == TurnDirection.NONE:
                self._motor_stop()
            elif turn_direction == TurnDirection.LEFT:
                if turn_type == TurnType.SPIN:
                    self._motor_left(1, self.DIR_BACKWARD, speed_value)
                    self._motor_right(1, self.DIR_FORWARD, speed_value)
                elif turn_type == TurnType.PIVOT:
                    self._motor_left(0, self.DIR_FORWARD, 0)  # stop left motor
                    self._motor_right(1, self.DIR_FORWARD, speed_value)
                elif turn_type == TurnType.CURVE:
                    raise ValueError("CURVE not supported without thrust")
                else:
                    raise ValueError("Turn type should be SPIN or PIVOT for NONE thrust")
            elif turn_direction == TurnDirection.RIGHT:
                if turn_type == TurnType.SPIN:
                    self._motor_left(1, self.DIR_FORWARD, speed_value)
                    self._motor_right(1, self.DIR_BACKWARD, speed_value)
                elif turn_type == TurnType.PIVOT:
                    self._motor_left(1, self.DIR_FORWARD, speed_value)
                    self._motor_right(0, self.DIR_FORWARD, 0)  # stop right motor
                elif turn_type == TurnType.CURVE:
                    raise ValueError("CURVE not supported without thrust")
                else:
                    raise ValueError("Turn type should be SPIN or PIVOT for NONE thrust")
            else:
                raise ValueError("Invalid turn direction")

    def cleanup(self):
        """Clean up GPIO resources"""
        self._motor_stop()
        # Stop PWM before cleanup
        if self.pwm_A:
            self.pwm_A.stop()
        if self.pwm_B:
            self.pwm_B.stop()
        GPIO.cleanup()
