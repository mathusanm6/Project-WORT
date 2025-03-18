import math
import threading
import time
from copy import deepcopy

from src.rasptank.movement.base_movement_controller import BaseMovementController
from src.rasptank.movement.movement_api import ThrustDirection, TurnDirection


class MockMovementController(BaseMovementController):
    """Mock implementation of movement controller for testing.
    Simulates the movement of a Rasptank in a 2D space with a background thread."""

    def __init__(self, simulation_speed_factor=1.0):
        """Initialize the mock movement controller with simulation parameters

        Args:
            simulation_speed_factor (float): Speed up factor for simulation (higher = faster simulation)
        """
        # Initialize state
        self._state = {
            "thrust_direction": "none",
            "turn_direction": "none",
            "speed": 0.0,
            "turn_factor": 0.0,
        }

        # Simulation parameters
        self.position = {
            "x": 0.0,
            "y": 0.0,
            "heading": 0.0,
        }  # x, y in meters, heading in degrees
        self.max_speed = 0.5 * simulation_speed_factor  # meters per second at 100% speed
        self.max_turn_rate = 90.0 * simulation_speed_factor  # degrees per second at 100% turn
        self.simulation_speed_factor = simulation_speed_factor

        # Thread control
        self.running = False
        self.simulation_thread = None
        self.lock = threading.Lock()  # For thread-safe access to position
        self.last_update_time = time.time()

        # Movement history
        self.movement_history = []

        # Timer for timed movements
        self.timer_lock = threading.Lock()
        self.pending_timers = {}

        # Start the simulation thread
        self.start_simulation()

        # Record initial state after everything is set up
        self._record_movement_state()

    def start_simulation(self):
        """Start the background simulation thread"""
        self.running = True
        self.simulation_thread = threading.Thread(target=self._simulation_loop)
        self.simulation_thread.daemon = True  # Thread will exit when main program exits
        self.simulation_thread.start()

    def stop_simulation(self):
        """Stop the simulation thread"""
        self.running = False
        if self.simulation_thread:
            self.simulation_thread.join(timeout=1.0)  # Wait for thread to finish

    def _simulation_loop(self):
        """Background thread that continuously updates the simulated position"""
        while self.running:
            # Calculate time elapsed since last update
            current_time = time.time()
            dt = current_time - self.last_update_time
            self.last_update_time = current_time

            # Update position based on current movement state
            self._update_position(dt)

            # Sleep a short time to avoid consuming too much CPU
            time.sleep(0.01)

    def _record_movement_state(self):
        """Record the current movement state and position in history"""
        with self.lock:
            entry = {
                "thrust_direction": self._state["thrust_direction"],
                "turn_direction": self._state["turn_direction"],
                "speed": self._state["speed"],
                "turn_factor": self._state["turn_factor"],
                "timestamp": time.time(),
                "simulated_position": deepcopy(self.position),
            }
            self.movement_history.append(entry)

            # Limit history size to prevent memory issues
            if len(self.movement_history) > 1000:
                self.movement_history = self.movement_history[-1000:]

    def _update_position(self, dt):
        """Update the simulated position based on elapsed time and current movement state"""
        with self.lock:
            # Extract movement parameters
            thrust_dir = self._state["thrust_direction"]
            turn_dir = self._state["turn_direction"]
            speed = self._state["speed"] / 100.0  # Convert percentage to 0-1 scale
            turn_factor = self._state["turn_factor"]

            # Calculate linear and angular velocities
            linear_speed = 0.0
            if thrust_dir == "forward":
                linear_speed = self.max_speed * speed
            elif thrust_dir == "backward":
                linear_speed = -self.max_speed * speed

            angular_speed = 0.0
            if turn_dir == "right":
                angular_speed = self.max_turn_rate * turn_factor
            elif turn_dir == "left":
                angular_speed = -self.max_turn_rate * turn_factor

            # Update heading (in degrees)
            self.position["heading"] += angular_speed * dt
            # Normalize heading to [0, 360]
            self.position["heading"] = self.position["heading"] % 360.0

            # Convert heading to radians for position calculations
            heading_rad = math.radians(self.position["heading"])

            # Update position based on heading and linear speed
            # Note: in this coordinate system, heading 0 is along positive y-axis
            self.position["x"] += linear_speed * math.sin(heading_rad) * dt
            self.position["y"] += linear_speed * math.cos(heading_rad) * dt

    def _validate_movement_params(self, thrust_direction, turn_direction, speed, turn_factor):
        """Validate and normalize movement parameters"""
        # Check thrust direction
        if thrust_direction == ThrustDirection.FORWARD:
            thrust_dir = "forward"
        elif thrust_direction == ThrustDirection.BACKWARD:
            thrust_dir = "backward"
        else:
            thrust_dir = "none"

        # Check turn direction
        if turn_direction == TurnDirection.LEFT:
            turn_dir = "left"
        elif turn_direction == TurnDirection.RIGHT:
            turn_dir = "right"
        else:
            turn_dir = "none"

        # Validate speed and turn factor
        validated_speed = max(0.0, min(100.0, speed))
        validated_turn_factor = max(0.0, min(1.0, turn_factor))

        return {
            "thrust_direction": thrust_dir,
            "turn_direction": turn_dir,
            "speed": validated_speed,
            "turn_factor": validated_turn_factor,
        }

    def move(self, thrust_direction, turn_direction, speed, turn_factor):
        """Implementation of move method that updates the movement state"""
        # Validate parameters
        validated_params = self._validate_movement_params(
            thrust_direction, turn_direction, speed, turn_factor
        )

        # Update internal state
        self._state = validated_params

        # Record the new state
        self._record_movement_state()

        # Return the current state
        return self._state.copy()

    def timed_move(self, thrust_direction, turn_direction, speed, turn_factor, duration):
        """Move for a specific duration, then stop

        Args:
            thrust_direction (ThrustDirection): Direction of movement
            turn_direction (TurnDirection): Direction of turning
            speed (float): Speed from 0-100
            turn_factor (float): Turn intensity from 0-1
            duration (float): Duration in seconds

        Returns:
            dict: Current motor state
        """
        # Apply the movement
        self.move(thrust_direction, turn_direction, speed, turn_factor)

        # Schedule a stop after the duration
        with self.timer_lock:
            timer_id = time.time()  # Use current time as unique ID
            timer = threading.Timer(duration, self._timed_move_callback, args=[timer_id])
            self.pending_timers[timer_id] = timer
            timer.start()

        return self._state.copy()

    def _timed_move_callback(self, timer_id):
        """Callback for when a timed movement completes"""
        # Stop movement
        self.stop()

        # Remove the timer from pending timers
        with self.timer_lock:
            if timer_id in self.pending_timers:
                del self.pending_timers[timer_id]

    def stop(self):
        """Stop all movement"""
        self._state = {
            "thrust_direction": "none",
            "turn_direction": "none",
            "speed": 0.0,
            "turn_factor": 0.0,
        }

        # Record the stop state
        self._record_movement_state()

        return self._state.copy()

    def get_status(self):
        """Get the current movement status"""
        return self._state.copy()

    def get_simulated_position(self):
        """Get the current simulated position (thread-safe)"""
        with self.lock:
            return self.position.copy()

    def reset_simulation(self, x=0.0, y=0.0, heading=0.0):
        """Reset the simulated position and movement history

        Args:
            x (float): X coordinate to reset to
            y (float): Y coordinate to reset to
            heading (float): Heading in degrees to reset to
        """
        with self.lock:
            self.position = {"x": x, "y": y, "heading": heading}
            # Clear the movement history
            self.movement_history = []

        # Stop any current movement
        self._state = {
            "thrust_direction": "none",
            "turn_direction": "none",
            "speed": 0.0,
            "turn_factor": 0.0,
        }

        # Record initial state after reset (just one record)
        self._record_movement_state()

    def get_movement_history(self):
        """Get the history of movement commands and positions

        Returns:
            list: List of movement state entries
        """
        with self.lock:
            return deepcopy(self.movement_history)

    def cleanup(self):
        """Clean up resources (stop the simulation thread and cancel timers)"""
        # Cancel all pending timers
        with self.timer_lock:
            for timer_id in list(self.pending_timers.keys()):
                self.pending_timers[timer_id].cancel()
            self.pending_timers.clear()

        # Stop the simulation thread
        self.stop_simulation()
