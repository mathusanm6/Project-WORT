"""Interface for Rasptank movement functionality."""

from abc import ABC, abstractmethod
from enum import Enum
from typing import Any, Dict


class State(Enum):
    THRUST_DIRECTION = "thrust_direction"
    TURN_DIRECTION = "turn_direction"
    SPEED = "speed"
    TURN_FACTOR = "turn_factor"


class ThrustDirection(Enum):
    FORWARD = "forward"
    BACKWARD = "backward"
    NONE = "none"


class TurnDirection(Enum):
    LEFT = "left"
    RIGHT = "right"
    NONE = "none"


class MovementAPI(ABC):
    """Interface for Rasptank movement functionality."""

    @abstractmethod
    def move(
        self,
        thrust_direction: ThrustDirection,
        turn_direction: TurnDirection,
        speed: float,
        turn_factor: float,
    ) -> Dict[State, Any]:
        """Move the Rasptank.

        Args:
            thrust_direction (ThrustDirection): Thrust direction
            turn_direction (TurnDirection): Turn direction
            speed (float): Speed factor between 0.0 and 100.0
            turn_factor (float): Turning factor between 0.0 and 1.0 (affects the sharpness of the turn)

        Returns:
            dict: Current movement state after applying the movement
        """
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> Dict[State, Any]:
        """Immediately stop all movement.

        Returns:
            dict: Current movement state after stopping
        """
        raise NotImplementedError

    @abstractmethod
    def get_state(self) -> Dict[State, Any]:
        """Get the current movement state.

        Returns:
            dict: Current movement state
        """
        raise NotImplementedError
