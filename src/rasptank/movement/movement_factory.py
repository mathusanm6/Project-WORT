from enum import Enum

from src.rasptank.movement.default_movement_controller import DefaultMovementController
from src.rasptank.movement.mock_movement_controller import MockMovementController

# from mqtt_movement_controller import MQTTMovementController


class MovementControllerType(Enum):
    """Enumeration of movement controller types.

    Attributes:
        DEFAULT (int): Default movement controller
        MQTT (int): MQTT-based movement controller
        MOCK (int): Mock movement controller for testing
    """

    DEFAULT = 0
    MQTT = 1
    MOCK = 2


class MovementFactory:
    """Factory for creating movement implementations."""

    @staticmethod
    def create_movement_controller(controller_type=MovementControllerType.DEFAULT, **kwargs):
        """Create a movement controller based on the given type.

        Args:
            controller_type (MovementControllerType): Type of movement controller to create
            **kwargs: Additional configuration parameters

        Returns:
            MovementAPI: An implementation of the MovementAPI interface
        """
        if controller_type == MovementControllerType.MQTT:
            # Return MQTT controller when implemented
            # return MQTTMovementController(**kwargs)
            raise NotImplementedError("MQTT controller not yet implemented")
        elif controller_type == MovementControllerType.MOCK:
            return MockMovementController(**kwargs)
        else:
            return DefaultMovementController(**kwargs)
