"""Default implementation of movement controller for Rasptank."""

import threading

# Import from src.common
from src.common.enum.movement import (
    CurvedTurnRate,
    SpeedMode,
    ThrustDirection,
    TurnDirection,
    TurnType,
)
from src.rasptank.hardware.hardware_main import RasptankHardware

# Import from src.rasptank
from src.rasptank.movement.controller.base import BaseMovementController


class DefaultMovementController(BaseMovementController):
    """Default implementation of movement controller for Rasptank.

    This controller directly interacts with the hardware to control the movement of the Rasptank.
    """

    def __init__(self, hardware: RasptankHardware):
        super().__init__()

        # Hardware-specific implementation
        self.hardware = hardware

        # For handling timed movements
        self.timer_lock = threading.Lock()
        self.pending_timers = {}

    def _apply_movement(
        self,
        thrust_direction: ThrustDirection,
        turn_direction: TurnDirection,
        turn_type: TurnType,
        speed_mode: SpeedMode,
        curved_turn_rate: CurvedTurnRate,
    ):
        """Apply the movement to the hardware."""

        # Apply movement to hardware
        self.hardware.move_rasptank_hardware(
            thrust_direction, turn_direction, turn_type, speed_mode, curved_turn_rate
        )

        # Return the updated state
        return self.update_state(
            thrust_direction, turn_direction, turn_type, speed_mode, curved_turn_rate
        )

    def cleanup(self):
        """Clean up resources"""
        # Cancel all pending timers
        with self.timer_lock:
            for timer_id in list(self.pending_timers.keys()):
                self.pending_timers[timer_id].cancel()
            self.pending_timers.clear()
