import logging
from abc import ABC, abstractmethod
from enum import Enum
from typing import Any


class LogLevel(Enum):
    """Log levels corresponding to standard logging levels."""

    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL


class Logger(ABC):
    """
    Abstract logger interface for the Rasptank project.

    This interface defines structured, context-aware logging methods
    with support for enrichment through persistent context.

    Usage:

        # TODO: Provide an example of how to use this logger interface.
    """

    @abstractmethod
    def debugw(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log a debug message with structured context."""
        pass

    @abstractmethod
    def infow(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log an info message with structured context."""
        pass

    @abstractmethod
    def warnw(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log a warning message with structured context."""
        pass

    @abstractmethod
    def errorw(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log an error message with structured context."""
        pass

    @abstractmethod
    def fatalw(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log a fatal message with structured context and terminate the program."""
        pass

    @abstractmethod
    def with_context(self, **kwargs: Any) -> "Logger":
        """Return a new logger with additional persistent context."""
        pass

    @abstractmethod
    def with_component(self, component: str) -> "Logger":
        """Return a new logger for a specific component."""
        pass

    @abstractmethod
    def with_node_id(self, node_id: str) -> "Logger":
        """Return a new logger for a specific node ID."""
        pass
