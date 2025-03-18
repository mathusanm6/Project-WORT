"""Defines the API contract for Rasptank movement system."""

from enum import Enum
from typing import Dict, Any


class ThrustDirection(Enum):
    FORWARD = "forward"
    BACKWARD = "backward"
    NONE = "none"


class TurnDirection(Enum):
    LEFT = "left"
    RIGHT = "right"
    NONE = "none"


class MovementAPI:
    """Interface contract for Rasptank movement functionality."""

    def move(
        self,
        thrust_direction: ThrustDirection,
        turn_direction: TurnDirection,
        speed: float,
        turn_factor: float,
    ) -> Dict[str, Any]:
        """Move the Rasptank in a given direction at a given speed for a given duration.

        Args:
            thrust_direction (ThrustDirection): Thrust direction ('forward', 'backward', or 'none')
            turn_direction (TurnDirection): Turn direction ('left', 'right', or 'none')
            speed (float): Speed factor between 0.0 and 100.0
            turn_factor (float): Turning factor between -1.0 (full left) and 1.0 (full right)

        Returns:
            dict: Current motor state after applying the movement command
        """
        pass

    def stop(self) -> Dict[str, Any]:
        """Immediately stop all movement.

        Returns:
            dict: Current motor state after stopping
        """
        pass

    def get_status(self) -> Dict[str, Any]:
        """Get the current movement status.

        Returns:
            dict: Current motor state
        """
        pass
