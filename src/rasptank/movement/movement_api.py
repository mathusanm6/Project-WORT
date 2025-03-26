"""Interface for Rasptank movement functionality."""

from abc import ABC, abstractmethod
from typing import Any

# Import from src.common
from src.common.enum.movement import (
    CurvedTurnRate,
    SpeedMode,
    ThrustDirection,
    TurnDirection,
    TurnType,
)


class State:
    """State of the Rasptank movement.

    Attributes:
        thrust_direction (ThrustDirection): Thrust direction. Defaults to ThrustDirection.NONE
        turn_direction (TurnDirection): Turn direction. Defaults to TurnDirection.NONE
        turn_type (TurnType): Turn type. Defaults to TurnType.NONE
        speed_mode (SpeedMode): Speed mode. Defaults to SpeedMode.STOP
        curved_turn_rate (CurvedTurnRate): Rate of turn for CURVE turn type (0.0 to 1.0 with 0.0 being no curve). Defaults to 0.0 (no curve)
    """

    def __init__(
        self,
        thrust_direction: ThrustDirection = ThrustDirection.NONE,
        turn_direction: TurnDirection = TurnDirection.NONE,
        turn_type: TurnType = TurnType.NONE,
        speed_mode: SpeedMode = SpeedMode.STOP,
        curved_turn_rate: CurvedTurnRate = CurvedTurnRate.NONE,
    ):
        self.thrust_direction = thrust_direction
        self.turn_direction = turn_direction
        self.turn_type = turn_type
        self.speed_mode = speed_mode
        self.curved_turn_rate = curved_turn_rate

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, State):
            return False
        return (
            self.thrust_direction == other.thrust_direction
            and self.turn_direction == other.turn_direction
            and self.turn_type == other.turn_type
            and self.speed_mode == other.speed_mode
            and self.curved_turn_rate == other.curved_turn_rate
        )


class MovementAPI(ABC):
    """Interface for Rasptank movement functionality."""

    @abstractmethod
    def move(
        self,
        thrust_direction: ThrustDirection,
        turn_direction: TurnDirection,
        turn_type: TurnType,
        speed_mode: SpeedMode,
        curved_turn_rate: CurvedTurnRate,
    ) -> State:
        """Move the Rasptank.

        Args:
            thrust_direction (ThrustDirection, optional): Thrust direction. Defaults to ThrustDirection.NONE.
            turn_direction (TurnDirection, optional): Turn direction. Defaults to TurnDirection.NONE.
            turn_type (TurnType, optional): Turn type. Defaults to TurnType.NONE.
            speed_mode (SpeedMode, optional): Speed mode. Defaults to SpeedMode.STOP.
            curved_turn_rate (CurvedTurnRate, optional): Rate of turn for CURVE turn type (0.0 to 1.0 with 0.0 being no curve). Defaults to 0.0.

        Returns:
            State: Current movement state after moving
        """
        raise NotImplementedError

    @abstractmethod
    def stop(self) -> State:
        """Immediately stop all movement.

        Returns:
            State: Current movement state after stopping (ThrustDirection.NONE, TurnDirection.NONE, TurnType.NONE, SpeedMode.STOP, 0.0)
        """
        raise NotImplementedError

    @abstractmethod
    def get_state(self) -> State:
        """Get the current movement state.

        Returns:
            State: Current movement state
        """
        raise NotImplementedError
