"""Base implementation of the MovementAPI interface with abstract hardware-specific methods."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Tuple

from src.rasptank.movement.movement_api import MovementAPI, State, ThrustDirection, TurnDirection


class BaseMovementController(MovementAPI, ABC):
    """Base implementation of the MovementAPI interface with abstract hardware-specific methods."""

    def __init__(self):
        self._state: Dict[State, Any] = {
            State.THRUST_DIRECTION: ThrustDirection.NONE,
            State.TURN_DIRECTION: TurnDirection.NONE,
            State.SPEED: 0.0,
            State.TURN_FACTOR: 0.0,
        }

    def move(
        self,
        thrust_direction: ThrustDirection,
        turn_direction: TurnDirection,
        speed: float,
        turn_factor: float,
    ) -> Dict[State, Any]:
        validated_params = self._validate_movement_params(
            thrust_direction, turn_direction, speed, turn_factor
        )
        return self._apply_movement(*validated_params)

    def stop(self) -> Dict[State, Any]:
        return self._apply_movement(ThrustDirection.NONE, TurnDirection.NONE, 0.0, 0.0)

    def get_state(self) -> Dict[State, Any]:
        return self._state.copy()

    def _validate_movement_params(
        self,
        thrust_direction: ThrustDirection,
        turn_direction: TurnDirection,
        speed: float,
        turn_factor: float,
    ) -> Tuple[ThrustDirection, TurnDirection, float, float]:
        """Validate the movement parameters and return a sanitized dictionary.

        Args:
            thrust_direction (ThrustDirection): Thrust direction
            turn_direction (TurnDirection): Turn direction
            speed (float): Speed factor between 0.0 and 100.0
            turn_factor (float): Turning factor between 0.0 and 1.0 (affects the sharpness of the turn)

        Returns:
            tuple: Sanitized movement parameters (thrust_direction, turn_direction, speed, turn_factor)
        """
        return (
            thrust_direction,
            turn_direction,
            max(0.0, min(100.0, speed)),
            max(0.0, min(1.0, turn_factor)),
        )

    def _apply_movement(
        self,
        thrust_direction: ThrustDirection,
        turn_direction: TurnDirection,
        speed: float,
        turn_factor: float,
    ) -> Dict[State, Any]:
        """Apply movement based on the given parameters.

        Args:
            thrust_direction (ThrustDirection): Thrust direction
            turn_direction (TurnDirection): Turn direction
            speed (float): Speed factor between 0.0 and 100.0
            turn_factor (float): Turning factor between 0.0 and 1.0 (affects the sharpness of the turn)

        Returns:
            dict: Current movement state after applying the movement
        """
        raise NotImplementedError
