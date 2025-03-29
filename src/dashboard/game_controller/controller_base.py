"""
Base controller module providing generic game controller interface logic.
This module handles the common functionality for all game controllers.
"""

import threading
import time
from typing import Dict

import pygame

from src.common.logging.logger_api import Logger


class BaseController:
    """Base class for game controllers using pygame."""

    def __init__(self, base_controller_logger: Logger):
        """Initialize base controller state and resources."""
        self.logger = base_controller_logger
        self.logger.infow("Initializing base controller")
        # Initialize controller state
        self.controller_state = {"is_connected": False}

        # Initialize pygame joystick
        self.joystick = None
        self.controller_id = 0

        # States for tracking changes
        self.button_states = {}
        self.prev_button_states = {}
        self.axis_states = {}
        self.prev_axis_states = {}

        # Threading for controller polling
        self.polling_thread = None
        self.stop_event = threading.Event()

        self.logger.infow("Base controller initialized")

    def setup(self, max_retries=3) -> bool:
        """Initialize and set up the controller using pygame.

        Args:
            max_retries (int): Maximum number of connection attempts

        Returns:
            bool: True if successfully set up, False otherwise
        """
        for attempt in range(max_retries):
            try:
                self.logger.infow(
                    "Initializing controller", "attempt", attempt + 1, "max_retries", max_retries
                )

                # Initialize pygame if not already done
                if not pygame.get_init():
                    pygame.init()

                # Initialize the joystick subsystem if not already done
                if not pygame.joystick.get_init():
                    pygame.joystick.init()

                # Check if any joystick is connected
                joystick_count = pygame.joystick.get_count()
                if joystick_count == 0:
                    self.logger.warnw("No joysticks found. Please connect a controller.")
                    time.sleep(1)
                    continue

                # Initialize the joystick
                self.joystick = pygame.joystick.Joystick(self.controller_id)
                self.joystick.init()

                # Log controller information
                controller_name = self.joystick.get_name()
                self.logger.infow("Connected to controller", "controller_name", controller_name)
                self.logger.infow(
                    "Controller info",
                    "num_axes",
                    self.joystick.get_numaxes(),
                    "num_buttons",
                    self.joystick.get_numbuttons(),
                )

                try:
                    self.logger.infow("Hat info", "num_hats", self.joystick.get_numhats())
                except:
                    self.logger.infow("Hat detection not supported")

                # Initialize controller states
                self._init_controller_states()

                self.controller_state["is_connected"] = True
                self.logger.infow("Controller initialized successfully")

                return True

            except Exception as e:
                self.logger.errorw("Error initializing controller", "error", str(e))
                time.sleep(1)  # Short delay before retry

        self.logger.warnw("Could not initialize controller after multiple attempts")
        return False

    def _init_controller_states(self):
        """Initialize button and axis states.

        This method should be overridden by subclasses to initialize
        controller-specific state.
        """
        # Initialize button states
        for i in range(self.joystick.get_numbuttons()):
            self.button_states[i] = False
            self.prev_button_states[i] = False

        # Initialize axis states
        for i in range(self.joystick.get_numaxes()):
            self.axis_states[i] = 0.0
            self.prev_axis_states[i] = 0.0

    def start(self, use_threading=True):
        """Start listening for controller events.

        Args:
            use_threading (bool): Whether to use a separate thread for polling

        Returns:
            bool: True if started successfully, False otherwise
        """
        if not pygame.get_init():
            pygame.init()

        if not pygame.joystick.get_init():
            pygame.joystick.init()

        if not self.controller_state["is_connected"]:
            if not self.setup():
                self.logger.errorw("Failed to start controller: No controller connected")
                return False

        # Start polling
        if use_threading:
            self.stop_event.clear()
            self.polling_thread = threading.Thread(target=self._polling_loop)
            self.polling_thread.daemon = True
            self.polling_thread.start()
            self.logger.infow("Controller polling thread started")

        return True

    def _polling_loop(self):
        """Main polling loop for controller events."""
        while not self.stop_event.is_set():
            self._process_events()
            time.sleep(0.01)  # Poll at ~100Hz

    def _process_events(self):
        """
        Process all pygame events and update controller state.
        This should be called from the main thread on macOS.
        """
        try:
            # Process all pygame events
            pygame.event.pump()

            # Update controller state based on current values
            self._read_controller_state()

        except pygame.error as e:
            self.logger.errorw("Pygame error during event processing", "error", str(e))
            # If we lost connection to the controller, try to recover
            if "Invalid joystick device number" in str(e):
                self.controller_state["is_connected"] = False
                self.logger.warnw("Controller disconnected. Attempting to reconnect...")
                time.sleep(0.5)
                self.setup(max_retries=1)
        except Exception as e:
            self.logger.errorw("Error processing controller events", "error", str(e))

    def _read_controller_state(self):
        """
        Read the current state of the controller.

        This method should be overridden by subclasses to handle
        controller-specific state reading and event triggering.
        """
        pass

    def get_status(self) -> Dict:
        """Get the current controller status.

        Returns:
            Dict: Controller status information
        """
        return {"connected": self.controller_state["is_connected"]}

    def stop(self):
        """Stop listening for controller events."""
        self.stop_event.set()
        if self.polling_thread and self.polling_thread.is_alive():
            self.polling_thread.join(timeout=1.0)

    def cleanup(self):
        """Clean up resources."""
        self.logger.infow("Cleaning up controller resources")

        self.stop()

        # Close pygame joystick
        if self.joystick:
            try:
                self.logger.infow("Closing controller")
                self.joystick.quit()
                self.controller_state["is_connected"] = False
            except Exception as e:
                self.logger.errorw("Error closing controller", "error", str(e))
