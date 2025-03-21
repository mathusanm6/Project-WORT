"""
DualSense controller mapping module.
This module contains button and axis mappings for the DualSense controller
across different platforms.
"""

import sys

# Platform detection
IS_MACOS = sys.platform == "darwin"
IS_WINDOWS = sys.platform.startswith("win")
IS_LINUX = sys.platform.startswith("linux")

# DualSense Button Mappings
if IS_MACOS:
    # macOS DualSense mappings
    BUTTON_MAPPING = {
        "cross": 0,  # X button
        "circle": 1,  # Circle button
        "square": 2,  # Square button
        "triangle": 3,  # Triangle button
        "L1": 9,  # Left shoulder
        "R1": 10,  # Right shoulder
        # "L2": 7,         # Left trigger (digital)
        # "R2": 8,         # Right trigger (digital)
        "share": 4,  # Create/Share button
        "options": 6,  # Options button
        "PS": 5,  # PlayStation button
        "L3": 7,  # Left stick press
        "R3": 8,  # Right stick press
        "touchpad": 15,  # Touchpad button
    }

    AXIS_MAPPING = {
        "left_x": 0,  # Left stick X axis
        "left_y": 1,  # Left stick Y axis
        "right_x": 2,  # Right stick X axis
        "right_y": 3,  # Right stick Y axis
        "L2": 4,  # Left trigger (analog)
        "R2": 5,  # Right trigger (analog)
    }

    DPAD_TYPE = "buttons"

    DPAD_BUTTON_MAPPING = {
        "up": 11,
        "down": 12,
        "left": 13,
        "right": 14,
    }

elif IS_WINDOWS:
    # Windows DualSense mappings
    BUTTON_MAPPING = {
        "cross": 0,  # X button
        "circle": 1,  # Circle button
        "square": 2,  # Square button
        "triangle": 3,  # Triangle button
        "L1": 4,  # Left shoulder
        "R1": 5,  # Right shoulder
        "L2": 6,  # Left trigger (digital)
        "R2": 7,  # Right trigger (digital)
        "share": 8,  # Create/Share button
        "options": 9,  # Options button
        "PS": 10,  # PlayStation button
        "L3": 11,  # Left stick press
        "R3": 12,  # Right stick press
        "touchpad": 13,  # Touchpad button
    }

    AXIS_MAPPING = {
        "left_x": 0,  # Left stick X axis
        "left_y": 1,  # Left stick Y axis
        "right_x": 2,  # Right stick X axis
        "right_y": 3,  # Right stick Y axis
        "L2": 4,  # Left trigger (analog)
        "R2": 5,  # Right trigger (analog)
    }

    # D-Pad implementation on Windows
    DPAD_TYPE = "hat"  # Options: "hat", "buttons", "axes"

    # If D-Pad is implemented as buttons
    DPAD_BUTTON_MAPPING = {
        "up": 14,
        "down": 15,
        "left": 16,
        "right": 17,
    }

    # If D-Pad is implemented as axes
    DPAD_AXIS_MAPPING = {
        "x": 6,  # -1 for left, 1 for right
        "y": 7,  # -1 for up, 1 for down
    }

else:  # Default Linux mappings
    # Linux DualSense mappings
    BUTTON_MAPPING = {
        "cross": 0,  # X button
        "circle": 1,  # Circle button
        "square": 2,  # Square button
        "triangle": 3,  # Triangle button
        "L1": 4,  # Left shoulder
        "R1": 5,  # Right shoulder
        "L2": 6,  # Left trigger (digital)
        "R2": 7,  # Right trigger (digital)
        "share": 8,  # Create/Share button
        "options": 9,  # Options button
        "PS": 10,  # PlayStation button
        "L3": 11,  # Left stick press
        "R3": 12,  # Right stick press
        "touchpad": 13,  # Touchpad button
    }

    AXIS_MAPPING = {
        "left_x": 0,  # Left stick X axis
        "left_y": 1,  # Left stick Y axis
        "right_x": 3,  # Right stick X axis
        "right_y": 4,  # Right stick Y axis
        "L2": 2,  # Left trigger (analog)
        "R2": 5,  # Right trigger (analog)
    }

    # D-Pad implementation on Linux
    DPAD_TYPE = "hat"  # Options: "hat", "buttons", "axes"

    # If D-Pad is implemented as buttons
    DPAD_BUTTON_MAPPING = {
        "up": 14,
        "down": 15,
        "left": 16,
        "right": 17,
    }

    # If D-Pad is implemented as axes
    DPAD_AXIS_MAPPING = {
        "x": 6,  # -1 for left, 1 for right
        "y": 7,  # -1 for up, 1 for down
    }


# Utility functions for button/axis name lookup
def get_button_name(button_id):
    """Get button name from button ID.

    Args:
        button_id (int): Button ID

    Returns:
        str: Button name or None if not found
    """
    for name, id in BUTTON_MAPPING.items():
        if id == button_id:
            return name
    return None


def get_button_id(button_name):
    """Get button ID from button name.

    Args:
        button_name (str): Button name

    Returns:
        int: Button ID or None if not found
    """
    return BUTTON_MAPPING.get(button_name)


def get_axis_name(axis_id):
    """Get axis name from axis ID.

    Args:
        axis_id (int): Axis ID

    Returns:
        str: Axis name or None if not found
    """
    for name, id in AXIS_MAPPING.items():
        if id == axis_id:
            return name
    return None


def get_axis_id(axis_name):
    """Get axis ID from axis name.

    Args:
        axis_name (str): Axis name

    Returns:
        int: Axis ID or None if not found
    """
    return AXIS_MAPPING.get(axis_name)
