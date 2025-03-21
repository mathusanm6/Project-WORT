"""Test Rasptank by performing a series of stunts.

This script demonstrates the capabilities of the Rasptank by performing a series of stunts.
The stunts include moving forward, turning right, turning left, spinning in place, and moving backward.
"""

import threading
import time

from src.rasptank.movement.controller.default import DefaultMovementController
from src.rasptank.movement.movement_api import ThrustDirection, TurnDirection
from src.rasptank.movement.movement_factory import MovementControllerType, MovementFactory


def continuous_movement(
    default_movement_controller: DefaultMovementController,
    thrust_direction: ThrustDirection,
    turn_dir: TurnDirection,
    speed: float,
    turn_intensity: float,
    duration: float,
):
    """Continuously send movement commands for the specified duration"""
    end_time = time.time() + duration
    while time.time() < end_time:
        default_movement_controller.move(thrust_direction, turn_dir, speed, turn_intensity)
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
            default_movement_controller, ThrustDirection.FORWARD, TurnDirection.RIGHT, 100.0, 0.8, 5
        )

        # Turn left while moving forward
        print("Turning left...")
        continuous_movement(
            default_movement_controller, ThrustDirection.FORWARD, TurnDirection.LEFT, 100.0, 0.8, 5
        )

        # Spin in place (right)
        print("Spinning right...")
        continuous_movement(
            default_movement_controller, ThrustDirection.NONE, TurnDirection.RIGHT, 100.0, 1.0, 5
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
    default_movement_controller = MovementFactory.create_movement_controller(
        MovementControllerType.DEFAULT
    )
    do_stunt(default_movement_controller)
