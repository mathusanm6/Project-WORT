"""This module contains the constants for the actions of the Rasptank."""

from enum import Enum


class ActionType(Enum):
    """This class contains the action types for the actions of the Rasptank.

    Attributes:
        SHOOT (str): The shoot action.
    """

    SHOOT = "shoot"


# MQTT Topics
SHOOT_COMMAND_TOPIC = "rasptank/shoot/command"
