import time
import threading

from rasptank_hardware import RasptankHardware

class DefaultMovementController:
    """Default implementation of movement controller for Rasptank"""
    
    def __init__(self):
        """Initialize the movement controller with hardware access"""
        # Initialize hardware adapter
        self.hardware = RasptankHardware()
        
        # Track current state
        self.state = {
            "thrust_direction": "none",
            "turn_direction": "none",
            "speed": 0.0,
            "turn_factor": 0.0,
        }
        
        # For handling timed movements
        self.timer_lock = threading.Lock()
        self.pending_timers = {}
    
    def stop(self):
        """Immediately stop all movement
        
        Returns:
            dict: Current motor state after stopping
        """
        self.hardware.motor_stop()
        self.state = {"thrust_direction": "none", "turn_direction": "none", "speed": 0.0, "turn_factor": 0.0}
        return self.state
    
    def _apply_movement(self, motor_values):
        """Apply the calculated motor values to actual motors"""
        # Extract values for hardware adapter
        thrust_direction = motor_values["thrust_direction"]
        turn_direction = motor_values["turn_direction"]
        speed = motor_values["speed"]
        turn_factor = motor_values["turn_factor"]
        
        # Apply movement to hardware
        self.hardware.move_hardware(thrust_direction, turn_direction, speed, turn_factor)
        
        # Update and return current state
        self.state = {
            "thrust_direction": thrust_direction,
            "turn_direction": turn_direction,
            "speed": speed,
            "turn_factor": turn_factor,
        }
        
        return self.state
    
    def _schedule_stop(self, duration):
        """Schedule a stop after the specified duration (in ms)"""
        timer_id = f"timer-{time.time()}"
        
        def stop_callback():
            self.stop()
            with self.timer_lock:
                if timer_id in self.pending_timers:
                    del self.pending_timers[timer_id]
        
        # Create and start timer
        timer = threading.Timer(duration / 1000.0, stop_callback)
        timer.daemon = True
        
        with self.timer_lock:
            self.pending_timers[timer_id] = timer
            
        timer.start()
        return timer_id
    
    def cleanup(self):
        """Clean up resources"""
        # Cancel all pending timers
        with self.timer_lock:
            for timer_id in list(self.pending_timers.keys()):
                self.pending_timers[timer_id].cancel()
            self.pending_timers.clear()
        
        # Clean up hardware resources
        self.hardware.cleanup()