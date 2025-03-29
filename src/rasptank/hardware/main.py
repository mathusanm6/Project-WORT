"""Hardware-specific implementation for Rasptank."""

import logging
from queue import Queue

from RPi import GPIO

# Import from src.common
from src.common.enum.movement import (
    CurvedTurnRate,
    SpeedMode,
    ThrustDirection,
    TurnDirection,
    TurnType,
)
from src.rasptank.hardware.infrared import InfraEmitter, InfraReceiver
from src.rasptank.hardware.led_strip import RasptankLedStrip
from src.rasptank.hardware.motors import Direction, RasptankMotors
from src.rasptank.hardware.tracking_module import TrackingModule


class RasptankHardware:
    """Hardware-specific implementation for Rasptank."""

    def __init__(self):
        # Initialize GPIO
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)

        # Initialize motor controller
        self.motors = RasptankMotors()

        # Initialize LED strip
        self.led_strip = RasptankLedStrip()
        self.led_command_queue = Queue()

        # Initialize IR emitter
        self.ir_emitter = InfraEmitter()

        # Initialize IR receiver
        self.ir_receiver = InfraReceiver()

        # Initialize tracking module
        self.tracking_module = TrackingModule()

    def get_led_command_queue(self):
        """Get the LED command queue."""
        return self.led_command_queue

    def move_rasptank_hardware(
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
                self.motors.motor_left(1, Direction.FORWARD, speed_value)
                self.motors.motor_right(1, Direction.FORWARD, speed_value)
            elif turn_direction == TurnDirection.LEFT:
                if turn_type == TurnType.CURVE:
                    self.motors.motor_left(
                        1, Direction.FORWARD, int(speed_value * (1 - curved_turn_rate_value))
                    )
                    self.motors.motor_right(1, Direction.FORWARD, speed_value)
                else:
                    raise ValueError("Turn type must be CURVE for FORWARD + LEFT")
            elif turn_direction == TurnDirection.RIGHT:
                if turn_type == TurnType.CURVE:
                    self.motors.motor_left(1, Direction.FORWARD, speed_value)
                    self.motors.motor_right(
                        1, Direction.FORWARD, int(speed_value * (1 - curved_turn_rate_value))
                    )
                else:
                    raise ValueError("Turn type must be CURVE for FORWARD + RIGHT")
            else:
                raise ValueError("Invalid turn direction")
            return

        # Backward movement handling
        if thrust_direction == ThrustDirection.BACKWARD:
            if turn_direction == TurnDirection.NONE:
                self.motors.motor_left(1, Direction.BACKWARD, speed_value)
                self.motors.motor_right(1, Direction.BACKWARD, speed_value)
            elif turn_direction == TurnDirection.LEFT:
                if turn_type == TurnType.CURVE:
                    self.motors.motor_left(
                        1, Direction.BACKWARD, int(speed_value * (1 - curved_turn_rate_value))
                    )
                    self.motors.motor_right(1, Direction.BACKWARD, speed_value)
                else:
                    raise ValueError("Turn type must be CURVE for BACKWARD + LEFT")
            elif turn_direction == TurnDirection.RIGHT:
                if turn_type == TurnType.CURVE:
                    self.motors.motor_left(1, Direction.BACKWARD, speed_value)
                    self.motors.motor_right(
                        1, Direction.BACKWARD, int(speed_value * (1 - curved_turn_rate_value))
                    )
                else:
                    raise ValueError("Turn type must be CURVE for BACKWARD + RIGHT")
            else:
                raise ValueError("Invalid turn direction")
            return

        # No thrust (stationary) handling
        if thrust_direction == ThrustDirection.NONE:
            if turn_direction == TurnDirection.NONE:
                self.motors.motor_stop()
            elif turn_direction == TurnDirection.LEFT:
                if turn_type == TurnType.SPIN:
                    self.motors.motor_left(1, Direction.BACKWARD, speed_value)
                    self.motors.motor_right(1, Direction.FORWARD, speed_value)
                elif turn_type == TurnType.PIVOT:
                    self.motors.motor_left(0, Direction.FORWARD, 0)  # stop left motor
                    self.motors.motor_right(1, Direction.FORWARD, speed_value)
                elif turn_type == TurnType.CURVE:
                    raise ValueError("CURVE not supported without thrust")
                else:
                    raise ValueError("Turn type should be SPIN or PIVOT for NONE thrust")
            elif turn_direction == TurnDirection.RIGHT:
                if turn_type == TurnType.SPIN:
                    self.motors.motor_left(1, Direction.FORWARD, speed_value)
                    self.motors.motor_right(1, Direction.BACKWARD, speed_value)
                elif turn_type == TurnType.PIVOT:
                    self.motors.motor_left(1, Direction.FORWARD, speed_value)
                    self.motors.motor_right(0, Direction.FORWARD, 0)  # stop right motor
                elif turn_type == TurnType.CURVE:
                    raise ValueError("CURVE not supported without thrust")
                else:
                    raise ValueError("Turn type should be SPIN or PIVOT for NONE thrust")
            else:
                raise ValueError("Invalid turn direction")

    def blast_ir(self, verbose: bool = False):
        """Blast an IR signal."""
        return self.ir_emitter.blast(verbose=verbose)

    def is_on_top_of_capture_zone(self) -> bool:
        """Check if the Rasptank is on top of the capture zone."""
        return self.tracking_module.is_white_in_middle()

    def cleanup(self):
        """Clean up rasptank hardware."""
        logging.info("Cleaning up Rasptank hardware...")

        # Clean up motors
        self.motors.cleanup()

        # Clean up LED strip
        self.led_strip.cleanup()

        # Clean up IR emitter
        self.ir_emitter.cleanup()

        # Clean up IR receiver
        self.ir_receiver.cleanup()

        # GPIO cleanup
        GPIO.cleanup()

        logging.info("Rasptank hardware cleanup complete")
