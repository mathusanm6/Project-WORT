import threading
import time

from src.rasptank.movement.default_movement_controller import DefaultMovementController
from src.rasptank.movement.movement_api import ThrustDirection, TurnDirection
from src.rasptank.movement.movement_factory import MovementControllerType, MovementFactory


def setup():
    return MovementFactory.create_movement_controller(MovementControllerType.DEFAULT)


def continuous_movement(controller, thrust_dir, turn_dir, speed, turn_intensity, duration):
    """Continuously send movement commands for the specified duration"""
    end_time = time.time() + duration
    while time.time() < end_time:
        controller.move(thrust_dir, turn_dir, speed, turn_intensity)
        time.sleep(0.1)  # Send command every 0.1 seconds


def do_stunt(default_movement_controller: DefaultMovementController):
    try:
        # Move forward at 100% speed
        print("Moving forward at 100% speed...")
        continuous_movement(
            default_movement_controller, ThrustDirection.FORWARD, TurnDirection.NONE, 100.0, 0.0, 5
        )

        # Turn right while moving forward
        print("Turning right...")
        continuous_movement(
            default_movement_controller, ThrustDirection.FORWARD, TurnDirection.RIGHT, 100.0, 0.6, 5
        )

        # Turn left while moving forward
        print("Turning left...")
        continuous_movement(
            default_movement_controller, ThrustDirection.FORWARD, TurnDirection.LEFT, 100.0, 0.6, 5
        )

        # Spin in place (left)
        print("Spinning left...")
        continuous_movement(
            default_movement_controller, ThrustDirection.NONE, TurnDirection.LEFT, 100.0, 1.0, 5
        )

        # Move backward
        print("Moving backward...")
        continuous_movement(
            default_movement_controller, ThrustDirection.BACKWARD, TurnDirection.NONE, 100.0, 0.0, 5
        )

        # Stop
        print("Stopping...")
        default_movement_controller.stop()

    except KeyboardInterrupt:
        print("Program interrupted")


if __name__ == "__main__":
    default_movement_controller = setup()
    do_stunt(default_movement_controller)
