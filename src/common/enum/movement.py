"""This module contains the enums for the movement of the Rasptank."""

from enum import Enum
from typing import List, Tuple


class ThrustDirection(Enum):
    """Possible thrust directions for the Rasptank are FORWARD, BACKWARD, and NONE.

    - FORWARD: Move forward
    - BACKWARD: Move backward
    - NONE: No movement (forward or backward)
    """

    FORWARD = "forward"
    BACKWARD = "backward"
    NONE = "none"


class TurnDirection(Enum):
    """Possible turn directions for the Rasptank are LEFT, RIGHT, and NONE.

    - LEFT: Turn left
    - RIGHT: Turn right
    - NONE: No turn
    """

    LEFT = "left"
    RIGHT = "right"
    NONE = "none"


class TurnType(Enum):
    """Possible turn types for the Rasptank are SPIN, CURVE, PIVOT, and NONE.

    - SPIN: In-place rotation with both tracks turning in opposite directions.
    - CURVE: Both tracks moving but at different speeds.
    - PIVOT: One track stationary, the other moves to swing the bot.
    - NONE: No turn
    """

    SPIN = "spin"
    CURVE = "curve"
    PIVOT = "pivot"
    NONE = "none"


class SpeedMode(Enum):
    """Possible speed modes for the Rasptank.

    The speed values are in the range of 0 to 100.
    """

    STOP = 0
    GEAR_1 = 70
    GEAR_2 = 80
    GEAR_3 = 90
    GEAR_4 = 100

    @property
    def color(self) -> Tuple[int, int, int]:
        if self.name == "STOP":
            return (255, 255, 255)
        elif self.name == "GEAR_1":
            return (135, 206, 250)
        elif self.name == "GEAR_2":
            return (67, 198, 252)
        elif self.name == "GEAR_3":
            return (0, 191, 255)
        elif self.name == "GEAR_4":
            return (0, 0, 139)
        else:
            raise ValueError(f"Invalid speed value: {self.name}")

    @staticmethod
    def get_speed_modes() -> List["SpeedMode"]:
        """Get all speed modes except STOP."""
        return [speed_mode for speed_mode in SpeedMode if speed_mode != SpeedMode.STOP]

    @staticmethod
    def get_speed_values() -> List[int]:
        """Get the speed values for all speed modes except STOP."""
        return [speed_mode.value for speed_mode in SpeedMode if speed_mode != SpeedMode.STOP]

    @staticmethod
    def for_display() -> List[str]:
        """Get the speed mode names except STOP for display."""
        return [
            f"{speed_mode.name} ({speed_mode.value}%)"
            for speed_mode in SpeedMode
            if speed_mode != SpeedMode.STOP
        ]


class CurvedTurnRate(Enum):
    """Possible curved turn rates for the Rasptank.

    The curved turn rates are in the range of 0.0 to 1.0.
    """

    NONE = 0.0
    LEVEL1 = 0.4
    LEVEL2 = 0.6

    @staticmethod
    def get_curved_turn_rates() -> List["CurvedTurnRate"]:
        """Get all curved turn rates except NONE."""
        return [
            curved_turn_rate
            for curved_turn_rate in CurvedTurnRate
            if curved_turn_rate != CurvedTurnRate.NONE
        ]

    @staticmethod
    def get_curved_turn_rate_values() -> List[float]:
        """Get the curved turn rate values for all curved turn rates except NONE."""
        return [
            curved_turn_rate.value
            for curved_turn_rate in CurvedTurnRate
            if curved_turn_rate != CurvedTurnRate.NONE
        ]

    @staticmethod
    def for_display() -> List[str]:
        """Get the curved turn rate names except NONE for display."""
        return [
            f"{curved_turn_rate.name} ({curved_turn_rate.value})"
            for curved_turn_rate in CurvedTurnRate
            if curved_turn_rate != CurvedTurnRate.NONE
        ]
