"""Factory for creating movement controllers."""

from enum import Enum

from src.rasptank.movement.controller.default import DefaultMovementController
from src.rasptank.movement.controller.mock import MockMovementController
from src.rasptank.movement.controller.mqtt import MQTTMovementController


class MovementControllerType(Enum):
    """Enumeration of movement controller types.

    Attributes:
        DEFAULT (int): Default movement controller
        MOCK (int): Mock movement controller for testing
        MQTT (int): MQTT-based movement controller
    """

    DEFAULT = 0
    MOCK = 1
    MQTT = 2


class MovementFactory:
    """Factory for creating movement controllers."""

    @staticmethod
    def create_movement_controller(
        controller_type: MovementControllerType = MovementControllerType.DEFAULT, **kwargs
    ):
        """Create a movement controller based on the given type `MovementControllerType`.

        Args:
            controller_type (MovementControllerType): Type of movement controller to create
            **kwargs: Additional configuration parameters

        Returns:
            BaseMovementController: Instance of the created movement controller
        """
        if controller_type == MovementControllerType.MQTT:
            return MQTTMovementController(**kwargs)
        elif controller_type == MovementControllerType.MOCK:
            return MockMovementController(**kwargs)
        else:
            return DefaultMovementController(**kwargs)
