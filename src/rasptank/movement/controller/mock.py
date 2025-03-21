"""Mock implementation of movement controller for testing."""

import math
import threading
import time
from copy import deepcopy
from enum import Enum
from typing import Any, Dict

from src.rasptank.movement.controller.base import BaseMovementController
from src.rasptank.movement.movement_api import State, ThrustDirection, TurnDirection


class MockState(Enum):
    THRUST_DIRECTION = State.THRUST_DIRECTION.value
    TURN_DIRECTION = State.TURN_DIRECTION.value
    SPEED = State.SPEED.value
    TURN_FACTOR = State.TURN_FACTOR.value
    TIMESTAMP = "timestamp"
    SIMULATED_POSITION = "simulated_position"


class Position:
    """Position in 2D space with x, y coordinates and heading."""

    def __init__(self, x: float = 0.0, y: float = 0.0, heading: float = 0.0):
        self.x = x  # X coordinate in meters
        self.y = y  # Y coordinate in meters
        self.heading = heading  # Heading in degrees


class MockMovementController(BaseMovementController):
    """Mock implementation of movement controller for testing.

    Simulates the movement of a Rasptank in a 2D space with a background thread.
    """

    def __init__(self, simulation_speed_factor=1.0):
        """Initialize the mock movement controller with simulation parameters

        Args:
            simulation_speed_factor (float): Speed up factor for simulation (higher = faster simulation)
        """
        super().__init__()

        # Simulation parameters
        self.position = Position()  # Current position of the simulated Rasptank
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
            state = self.get_state()
            entry = {
                MockState.THRUST_DIRECTION: state[MockState.THRUST_DIRECTION],
                MockState.TURN_DIRECTION: state[MockState.TURN_DIRECTION],
                MockState.SPEED: state[MockState.SPEED],
                MockState.TURN_FACTOR: state[MockState.TURN_FACTOR],
                MockState.TIMESTAMP: time.time(),
                MockState.SIMULATED_POSITION: deepcopy(self.position),
            }
            self.movement_history.append(entry)

            # Limit history size to prevent memory issues
            if len(self.movement_history) > 1000:
                self.movement_history = self.movement_history[-1000:]

    def _update_position(self, dt):
        """Update the simulated position based on elapsed time and current movement state"""
        with self.lock:
            state: MockState = self.get_state()
            # Extract movement parameters
            thrust_dir: ThrustDirection = state[MockState.THRUST_DIRECTION]
            turn_dir: TurnDirection = state[MockState.TURN_DIRECTION]
            speed: float = state[MockState.SPEED] / 100.0  # Convert percentage to 0-1 scale
            turn_factor: float = state[MockState.TURN_FACTOR]

            # Calculate linear and angular velocities
            linear_speed = 0.0
            if thrust_dir is ThrustDirection.FORWARD:
                linear_speed = self.max_speed * speed
            elif thrust_dir is ThrustDirection.BACKWARD:
                linear_speed = -self.max_speed * speed

            angular_speed = 0.0
            if turn_dir is TurnDirection.RIGHT:
                angular_speed = self.max_turn_rate * turn_factor
            elif turn_dir is TurnDirection.LEFT:
                angular_speed = -self.max_turn_rate * turn_factor

            # Update heading (in degrees)
            self.position.heading += angular_speed * dt
            # Normalize heading to [0, 360]
            self.position.heading = self.position.heading % 360.0

            # Convert heading to radians for position calculations
            heading_rad = math.radians(self.position.heading)

            # Update position based on heading and linear speed
            # Note: in this coordinate system, heading 0 is along positive y-axis
            self.position.x += linear_speed * math.sin(heading_rad) * dt
            self.position.y += linear_speed * math.cos(heading_rad) * dt

    def _apply_movement(
        self,
        thrust_direction: ThrustDirection,
        turn_direction: TurnDirection,
        speed: float,
        turn_factor: float,
    ) -> Dict[State, Any]:
        """Apply movement based on the given parameters

        Args:
            thrust_direction (ThrustDirection): Thrust direction
            turn_direction (TurnDirection): Turn direction
            speed (float): Speed factor between 0.0 and 100.0
            turn_factor (float): Turning factor between 0.0 and 1.0 (affects the sharpness of the turn)

        Returns:
            dict: Current movement state after applying the movement
        """
        with self.lock:
            # Update the movement state
            self._state = {
                MockState.THRUST_DIRECTION: thrust_direction,
                MockState.TURN_DIRECTION: turn_direction,
                MockState.SPEED: max(0.0, min(100.0, speed)),
                MockState.TURN_FACTOR: max(0.0, min(1.0, turn_factor)),
            }

            # Record the new state in the movement history
            self._record_movement_state()

            # Return a copy of the current state
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
            self.position = Position(x, y, heading)
            # Clear the movement history
            self.movement_history = []

        # Stop any current movement
        self.stop()

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
