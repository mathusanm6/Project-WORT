"""This module contains the Action class for the Rasptank.

The Action class is responsible for handling the actions of the Rasptank
such as shooting.
"""

from src.common.logging.logger_api import Logger
from src.rasptank.hardware.main import RasptankHardware


class ActionController:
    def __init__(self, action_logger: Logger, hardware: RasptankHardware):
        """Initialize the Action class.

        Args:
            hardware (RasptankHardware): The Rasptank hardware adapter.
        """
        self.logger = action_logger
        self.logger.infow("Initializing Action controller")
        self.hardware = hardware
        self.logger.infow("Action controller initialized")

    def shoot(self, verbose: bool = False):
        """Perform the shoot action.

        Returns:
            bool: True if the shoot action was successful, False otherwise.
        """
        self.logger.infow("Shooting action initiated", "verbose", verbose)
        return self.hardware.blast_ir(verbose=verbose)

    def cleanup(self):
        """Clean up resources."""
