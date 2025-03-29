from typing import Any, Union

from src.common.logging.console import ConsoleLogger
from src.common.logging.logger_api import Logger, LogLevel
from src.common.logging.no_op import NoOpLogger


class LoggerFactory:
    """
    Factory for creating loggers based on configuration.
    """

    @staticmethod
    def create_logger(
        logger_type: str = "console",
        name: str = "Rasptank",
        level: Union[LogLevel, str] = LogLevel.INFO,
        **kwargs: Any,
    ) -> Logger:
        """
        Create a logger of the specified type.

        Args:
            logger_type: Type of logger to create ("console", "noop", etc.)
            name: Logger name
            level: Logging level
            **kwargs: Additional configuration parameters for the specific logger type

        Returns:
            A logger instance
        """
        # Convert string level to LogLevel enum
        if isinstance(level, str):
            level = getattr(LogLevel, level.upper(), LogLevel.INFO)

        if logger_type == "console":
            return ConsoleLogger(name=name, level=level, **kwargs)
        elif logger_type == "noop":
            return NoOpLogger()
        else:
            # Default to console logger
            return ConsoleLogger(name=name, level=level)
