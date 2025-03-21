"""Default implementation of movement controller for Rasptank."""

import threading
import time

from src.rasptank.movement.controller.base import BaseMovementController
from src.rasptank.movement.movement_api import State, ThrustDirection, TurnDirection
from src.rasptank.movement.rasptank_hardware import RasptankHardware


class DefaultMovementController(BaseMovementController):
    """Default implementation of movement controller for Rasptank.

    This controller directly interacts with the hardware to control the movement of the Rasptank.
    """

    def __init__(self):
        super().__init__()

        # Initialize hardware adapter
        self.hardware = RasptankHardware()

        # For handling timed movements
        self.timer_lock = threading.Lock()
        self.pending_timers = {}

    def _apply_movement(
        self,
        thrust_direction: ThrustDirection,
        turn_direction: TurnDirection,
        speed: float,
        turn_factor: float,
    ):
        """Apply the movement to the hardware."""

        # Apply movement to hardware
        self.hardware.move_hardware(thrust_direction, turn_direction, speed, turn_factor)

        # Update state
        self._state = {
            State.THRUST_DIRECTION: thrust_direction,
            State.TURN_DIRECTION: turn_direction,
            State.SPEED: speed,
            State.TURN_FACTOR: turn_factor,
        }

        return self._state

    def cleanup(self):
        """Clean up resources"""
        # Cancel all pending timers
        with self.timer_lock:
            for timer_id in list(self.pending_timers.keys()):
                self.pending_timers[timer_id].cancel()
            self.pending_timers.clear()

        # Clean up hardware resources
        self.hardware.cleanup()
