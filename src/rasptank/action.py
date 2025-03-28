"""This module contains the Action class for the Rasptank.

The Action class is responsible for handling the actions of the Rasptank
such as shooting.
"""

from src.rasptank.hardware.main import RasptankHardware


class ActionController:
    def __init__(self, hardware: RasptankHardware):
        """Initialize the Action class.

        Args:
            hardware (RasptankHardware): The Rasptank hardware adapter.
        """
        self.hardware = hardware

    def shoot(self, verbose: bool = False):
        """Perform the shoot action.

        Returns:
            bool: True if the shoot action was successful, False otherwise.
        """
        return self.hardware.blast_ir(verbose=verbose)

    def cleanup(self):
        """Clean up resources."""
