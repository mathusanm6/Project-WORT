"""
Controller events module defining enums and types for controller events.
This module provides standardized event types and constants for controller events.
"""

from enum import Enum
from typing import Callable, Dict, NamedTuple


class ButtonEventType(Enum):
    """Types of button events."""

    PRESSED = "pressed"
    RELEASED = "released"


class JoystickPosition(NamedTuple):
    """Joystick position data."""

    x: float
    y: float


class TriggerValue(NamedTuple):
    """Trigger position data."""

    value: float


class DPadDirection(Enum):
    """D-pad directions."""

    UP = "up"
    DOWN = "down"
    LEFT = "left"
    RIGHT = "right"


class JoystickType(Enum):
    """Types of joysticks."""

    LEFT = "left"
    RIGHT = "right"


class TriggerType(Enum):
    """Types of triggers."""

    L2 = "L2"
    R2 = "R2"


class ButtonType(Enum):
    """Standard button names."""

    CROSS = "cross"  # PlayStation X button
    CIRCLE = "circle"
    SQUARE = "square"
    TRIANGLE = "triangle"
    L1 = "L1"
    R1 = "R1"
    L2 = "L2"  # Digital press of L2
    R2 = "R2"  # Digital press of R2
    L3 = "L3"  # Left stick press
    R3 = "R3"  # Right stick press
    SHARE = "share"  # Also called "Create" on PS5
    OPTIONS = "options"
    PS = "PS"  # PlayStation button
    TOUCHPAD = "touchpad"


# Type definitions for callback signatures
ButtonEventCallback = Callable[[str, bool], None]
JoystickEventCallback = Callable[[str, float, float], None]
TriggerEventCallback = Callable[[str, float], None]
DPadEventCallback = Callable[[str, bool], None]

# Complete controller state type
ControllerState = Dict[str, Dict]
