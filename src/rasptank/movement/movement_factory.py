from enum import Enum
from default_movement_controller import DefaultMovementController
from mock_movement_controller import MockMovementController
# from mqtt_movement_controller import MQTTMovementController

class MovementControllerType(Enum):
    """Enumeration of movement controller types.
    
    Attributes:
        DEFAULT (int): Default movement controller
        MQTT (int): MQTT-based movement controller
        MOCK (int): Mock movement controller
    """
    DEFAULT = 0
    MQTT = 1
    MOCK = 2

class MovementFactory:
    """Factory for creating movement implementations."""
    
    @staticmethod
    def create_movement_controller(controller_type: MovementControllerType = MovementControllerType.DEFAULT, **kwargs):
        """Create a movement controller based on the given type.
        
        Args:
            controller_type (MovementControllerType): Type of movement controller to create
            **kwargs: Additional configuration parameters
        
        Returns:
            MovementAPI: An implementation of the MovementAPI interface
        """
        # if controller_type == MovementControllerType.MQTT:
        #     return MQTTMovementController(**kwargs)
        if controller_type == MovementControllerType.MOCK:
            return MockMovementController(**kwargs)
        else:
            return DefaultMovementController(**kwargs)