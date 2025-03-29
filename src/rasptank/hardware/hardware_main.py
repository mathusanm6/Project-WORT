"""Hardware-specific implementation for Rasptank."""

from queue import Queue

from RPi import GPIO

from src.common.enum.movement import (
    CurvedTurnRate,
    SpeedMode,
    ThrustDirection,
    TurnDirection,
    TurnType,
)
from src.common.logging.decorators import log_function_call

# Import from src.common
from src.common.logging.logger_api import Logger
from src.common.logging.logger_factory import LoggerFactory

# Import hardware components
from src.rasptank.hardware.infrared import InfraEmitter, InfraReceiver
from src.rasptank.hardware.led_strip import RasptankLedStrip
from src.rasptank.hardware.motors import Direction, RasptankMotors
from src.rasptank.hardware.tracking_module import TrackingModule


class RasptankHardware:
    """Hardware-specific implementation for Rasptank."""

    def __init__(self, hw_logger: Logger):
        """Initialize the Rasptank hardware.

        Args:
            hw_logger (Logger, optional): Logger instance for hardware.
                If None, a default logger will be created.
        """
        self.logger = hw_logger

        self.logger.infow("Initializing Rasptank hardware")

        # Initialize GPIO
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)
        self.logger.debugw("GPIO initialized", "mode", "BCM")

        # Initialize motor controller
        self.motors = RasptankMotors()
        self.logger.debugw("Motors initialized")

        # Initialize LED strip
        led_strip_logger = hw_logger.with_component("LedStrip")
        self.led_strip = RasptankLedStrip(led_strip_logger)
        self.led_command_queue = Queue()
        self.logger.debugw("LED strip initialized")

        # Initialize IR emitter
        ir_emitter_logger = hw_logger.with_component("InfraEmitter")
        self.ir_emitter = InfraEmitter(ir_emitter_logger)

        # Initialize IR receiver
        ir_receiver_logger = hw_logger.with_component("InfraReceiver")
        self.ir_receiver = InfraReceiver(ir_receiver_logger)

        # Initialize tracking module
        self.tracking_module = TrackingModule()
        self.logger.debugw("Tracking module initialized")

        # For flag capture tracking
        self.capture_start_time = None

        self.logger.infow("Rasptank hardware successfully initialized")

    def get_led_command_queue(self):
        """Get the LED command queue."""
        return self.led_command_queue

    @log_function_call()
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

        self.logger.debugw(
            "Moving hardware",
            "thrust",
            thrust_direction.value,
            "turn",
            turn_direction.value,
            "type",
            turn_type.value,
            "speed",
            speed_value,
            "curve_rate",
            curved_turn_rate_value,
        )

        try:
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
        except ValueError as e:
            self.logger.errorw("Movement error", "error", str(e))
            raise

    def blast_ir(self, verbose: bool = False):
        """Blast an IR signal.

        Args:
            verbose (bool): Whether to log verbose information

        Returns:
            bool: True if the blast was successful, False otherwise
        """
        self.logger.debugw("Blasting IR signal", "verbose", verbose)
        return self.ir_emitter.blast(verbose=verbose)

    def is_on_top_of_capture_zone(self) -> bool:
        """Check if the Rasptank is on top of the capture zone.

        Returns:
            bool: True if the rasptank is on the capture zone, False otherwise
        """
        result = self.tracking_module.is_white_in_middle()
        self.logger.debugw("Capture zone check", "is_on_zone", result)
        return result

    def cleanup(self):
        """Clean up rasptank hardware."""
        self.logger.infow("Cleaning up Rasptank hardware")

        # Clean up motors
        try:
            self.motors.cleanup()
            self.logger.debugw("Motors cleaned up")
        except Exception as e:
            self.logger.errorw("Error cleaning up motors", "error", str(e))

        # Clean up LED strip
        try:
            self.led_strip.cleanup()
            self.logger.debugw("LED strip cleaned up")
        except Exception as e:
            self.logger.errorw("Error cleaning up LED strip", "error", str(e))

        # Clean up IR emitter
        try:
            self.ir_emitter.cleanup()
            self.logger.debugw("IR emitter cleaned up")
        except Exception as e:
            self.logger.errorw("Error cleaning up IR emitter", "error", str(e))

        # Clean up IR receiver
        try:
            self.ir_receiver.cleanup()
            self.logger.debugw("IR receiver cleaned up")
        except Exception as e:
            self.logger.errorw("Error cleaning up IR receiver", "error", str(e))

        # GPIO cleanup
        try:
            GPIO.cleanup()
            self.logger.debugw("GPIO cleaned up")
        except Exception as e:
            self.logger.errorw("Error cleaning up GPIO", "error", str(e))

        self.logger.infow("Rasptank hardware cleanup complete")
