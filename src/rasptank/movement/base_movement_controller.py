from rasptank.movement.movement_api import MovementAPI, ThrustDirection, TurnDirection

class BaseMovementController(MovementAPI):
    """Base implementation of the MovementAPI interface."""
    
    def __init__(self):
        self.state = {"thrust_direction": "none", "turn_direction": "none", "speed": 0.0, "turn_factor": 0.0}
    
    def move(self, thrust_direction: ThrustDirection, turn_direction: TurnDirection, speed: float, turn_factor: float):
        """Implementation of move method."""
        # Validation
        validated_params = self._validate_movement_params(thrust_direction, turn_direction, speed, turn_factor)
        
        # Apply movement
        result = self._apply_movement(**validated_params)
        
        # Handle timed movements if needed
        if validated_params["duration"] > 0:
            self._schedule_stop(validated_params["duration"])
        
        return result
    
    def stop(self):
        return self._apply_movement({"thrust_direction": "none", "turn_direction": "none", "speed": 0.0, "turn_factor": 0.0})
    
    def get_status(self):
        """Get the current movement status."""
        return self._state.copy()
    
    def _validate_movement_params(self, thrust_direction: ThrustDirection, turn_direction: TurnDirection, speed: float, turn_factor: float):
        """Validate and normalize movement parameters"""
        # Default implementation with basic validation
        return {
            "direction": thrust_direction.value if thrust_direction in ThrustDirection else "none",
            "rotation": turn_factor if turn_direction in TurnDirection else "none",
            "speed": max(0.0, min(100.0, speed)),
            "turn_factor": max(0.0, min(1.0, turn_factor)),
        }
    
    def _apply_movement(self, motor_values):
        """Apply the calculated motor values to actual motors"""
        # To be implemented by concrete classes
        self._state = motor_values
        return self._state
    
    def _schedule_stop(self, duration):
        """Schedule a stop after the specified duration"""
        # To be implemented by concrete classes
        pass