"""Base implementation of the MovementAPI interface with abstract hardware-specific methods."""

from abc import ABC, abstractmethod
from typing import Tuple

# Import from src.common
from src.common.enum.movement import (
    CurvedTurnRate,
    SpeedMode,
    ThrustDirection,
    TurnDirection,
    TurnType,
)

# Import from src.rasptank
from src.rasptank.movement.movement_api import MovementAPI, State


class BaseMovementController(MovementAPI, ABC):
    """Base implementation of the MovementAPI interface with abstract hardware-specific methods."""

    def __init__(self):
        self._state = (
            State()
        )  # (ThrustDirection.NONE, TurnDirection.NONE, TurnType.NONE, SpeedMode.STOP, CurvedTurnRate.NONE)

    # Override move method from MovementAPI
    def move(
        self,
        thrust_direction: ThrustDirection = ThrustDirection.NONE,
        turn_direction: TurnDirection = TurnDirection.NONE,
        turn_type: TurnType = TurnType.NONE,
        speed_mode: SpeedMode = SpeedMode.STOP,
        curved_turn_rate: CurvedTurnRate = CurvedTurnRate.NONE,
    ) -> State:
        return self._apply_movement(
            thrust_direction, turn_direction, turn_type, speed_mode, curved_turn_rate
        )

    # Override stop method from MovementAPI
    def stop(self) -> State:
        return self._apply_movement(
            ThrustDirection.NONE,
            TurnDirection.NONE,
            TurnType.NONE,
            SpeedMode.STOP,
            CurvedTurnRate.NONE,
        )

    # Override get_state method from MovementAPI
    def get_state(self) -> State:
        return self._state

    def update_state(
        self,
        thrust_direction: ThrustDirection = ThrustDirection.NONE,
        turn_direction: TurnDirection = TurnDirection.NONE,
        turn_type: TurnType = TurnType.NONE,
        speed_mode: SpeedMode = SpeedMode.STOP,
        curved_turn_rate: CurvedTurnRate = CurvedTurnRate.NONE,
    ) -> State:
        """Update the current state with the given movement parameters.

        Args:
            thrust_direction (ThrustDirection, optional): Thrust direction. Defaults to ThrustDirection.NONE.
            turn_direction (TurnDirection, optional): Turn direction. Defaults to TurnDirection.NONE.
            turn_type (TurnType, optional): Turn type. Defaults to TurnType.NONE.
            speed_mode (SpeedMode, optional): Speed mode. Defaults to SpeedMode.STOP.
            curved_turn_rate (CurvedTurnRate, optional): Rate of turn for CURVE turn type (0.0 to 1.0 with 0.0 being no curve). Defaults to CurvedTurnRate.NONE.

        Returns:
            State: Updated movement state
        """
        self._state = State(
            thrust_direction, turn_direction, turn_type, speed_mode, curved_turn_rate
        )
        return self._state

    @abstractmethod
    def _apply_movement(
        self,
        thrust_direction: ThrustDirection,
        turn_direction: TurnDirection,
        turn_type: TurnType,
        speed_mode: SpeedMode,
        curved_turn_rate: CurvedTurnRate,
    ) -> State:
        """Apply movement based on the given sanitized parameters.

        Args:
            thrust_direction (ThrustDirection): Thrust direction
            turn_direction (TurnDirection): Turn direction
            turn_type (TurnType): Turn type
            speed_mode (SpeedMode): Speed mode
            curved_turn_rate (CurvedTurnRate): Rate of turn for CURVE turn type (0.0 to 1.0 with 0.0 being no curve)

        Returns:
            State: Current movement state after applying the movement
        """
        raise NotImplementedError
