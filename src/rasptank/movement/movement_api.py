"""Defines the API contract for Rasptank movement system."""

from typing import Dict, Any


class MovementAPI:
    """Interface contract for Rasptank movement functionality."""
    
    def move(self, direction, speed, rotation=0.0, duration=0) -> Dict[str, Any]:
        """Move the Rasptank in a given direction at a given speed for a given duration.
        
        Args:
            direction (str): Direction of movement ('forward', 'backward', 'left', 'right', 'stop')
            speed (float): Speed factor between 0.0 and 1.0
            rotation (float): Rotation factor between -1.0 (left) and 1.0 (right)
            duration (int): Duration in ms (0 for continuous)
        
        Returns:
            dict: Current motor state after applying the movement command
        """
        pass
    
    def stop(self) -> Dict[str, Any]:
        """Immediately stop all movement.
        
        Returns:
            dict: Current motor state after stopping
        """
        pass
    
    def get_status(self) -> Dict[str, Any]:
        """Get the current movement status.
        
        Returns:
            dict: Current motor state
        """
        pass