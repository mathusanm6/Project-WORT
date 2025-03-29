from enum import Enum

from RPi import GPIO

from src.common.logging.logger_api import Logger


class TrackingModulePins(Enum):
    """Pin numbers for the tracking module."""

    RIGHT = 19
    MIDDLE = 16
    LEFT = 20


class TrackingModule:
    def __init__(self, tracking_module_logger: Logger):
        """Initialize the tracking module."""
        self.logger = tracking_module_logger
        self.logger.infow("Initializing tracking module")

        GPIO.setup(TrackingModulePins.RIGHT.value, GPIO.IN)
        GPIO.setup(TrackingModulePins.MIDDLE.value, GPIO.IN)
        GPIO.setup(TrackingModulePins.LEFT.value, GPIO.IN)

        self.logger.infow("Tracking module initialized")

    def _get_tracking_module_status(self):
        status_right = GPIO.input(TrackingModulePins.RIGHT.value)
        status_middle = GPIO.input(TrackingModulePins.MIDDLE.value)
        status_left = GPIO.input(TrackingModulePins.LEFT.value)
        return status_right, status_middle, status_left

    def is_white_in_middle(self) -> bool:
        _, status_middle, _ = self._get_tracking_module_status()
        return status_middle == 0
