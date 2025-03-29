import logging
import sys
from typing import Any, Dict, List, Tuple

from src.common.logging.logger_api import Logger, LogLevel

try:
    import colorama
    from colorama import Fore, Style

    colorama.init()
    COLOR_SUPPORT = True
except ImportError:
    COLOR_SUPPORT = False

    # Define dummy color constants if colorama is not available
    class DummyColors:
        def __getattr__(self, name):
            return ""

    Fore = Style = DummyColors()


def _format_value(v: Any) -> str:
    """Format a value for logging, with special handling for exceptions."""
    if isinstance(v, Exception):
        return f"{type(v).__name__}: {v}"
    return str(v)


def _process_key_values(keys_and_values: List[Any]) -> List[Tuple[str, Any]]:
    """Process key-value pairs, handling odd lengths and non-string keys."""
    result = []
    i = 0
    while i < len(keys_and_values) - 1:  # Stop one before the end to ensure pairs
        key = keys_and_values[i]
        value = keys_and_values[i + 1]

        # Only accept string keys
        if isinstance(key, str):
            result.append((key, value))
        i += 2
    return result


class ConsoleLogger(Logger):
    """
    A logger implementation that outputs to the console with optional color support.
    """

    def __init__(
        self,
        name: str = "Rasptank",
        level: LogLevel = LogLevel.INFO,
        context: Dict[str, Any] = None,
        use_colors: bool = True,
    ):
        self.name = name
        self.level = level.value if isinstance(level, LogLevel) else level
        self.context = context or {}
        self.use_colors = use_colors and COLOR_SUPPORT

        # Create the actual logger
        self.logger = logging.getLogger(name)
        self.logger.setLevel(self.level)

        # Set up handler if not already configured
        if not self.logger.handlers:
            self._setup_logger()

    def _setup_logger(self) -> None:
        """Set up the console logger with formatter."""
        handler = logging.StreamHandler()
        handler.setLevel(self.level)

        if self.use_colors:
            formatter = logging.Formatter(
                f"{Fore.CYAN}%(asctime)s{Style.RESET_ALL} "
                f"|{Fore.MAGENTA}%(levelname)-8s{Style.RESET_ALL}| "
                f"{Fore.YELLOW}%(name)s{Style.RESET_ALL} "
                f"- %(message)s"
            )
        else:
            formatter = logging.Formatter("%(asctime)s |%(levelname)-8s| %(name)s - %(message)s")

        handler.setFormatter(formatter)
        self.logger.addHandler(handler)

    def _format_context(self, extra_context: List[Tuple[str, Any]]) -> str:
        """Format all context key-value pairs for logging."""
        # Combine base context with extra context
        all_context = list(self.context.items()) + extra_context

        if not all_context:
            return ""

        if self.use_colors:
            parts = [
                f"{Fore.BLUE}{k}{Style.RESET_ALL}={Fore.GREEN}{_format_value(v)}{Style.RESET_ALL}"
                for k, v in all_context
            ]
        else:
            parts = [f"{k}={_format_value(v)}" for k, v in all_context]

        return " " + " ".join(parts)

    def _log(self, level: int, msg: str, *args: Any, **kwargs: Any) -> None:
        """Generic logging method that handles structured context."""
        if self.logger.isEnabledFor(level):
            # Process positional args as key-value pairs
            kv_pairs = _process_key_values(list(args))

            # Add kwargs as additional context
            for k, v in kwargs.items():
                kv_pairs.append((k, v))

            # Format message with context
            formatted_msg = msg + self._format_context(kv_pairs)

            # Log the message
            self.logger.log(level, formatted_msg)

    def debugw(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log a debug message with structured context."""
        self._log(logging.DEBUG, msg, *args, **kwargs)

    def infow(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log an info message with structured context."""
        self._log(logging.INFO, msg, *args, **kwargs)

    def warnw(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log a warning message with structured context."""
        if self.use_colors:
            msg = f"{Fore.YELLOW}{msg}{Style.RESET_ALL}"
        self._log(logging.WARNING, msg, *args, **kwargs)

    def errorw(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log an error message with structured context."""
        if self.use_colors:
            msg = f"{Fore.RED}{msg}{Style.RESET_ALL}"

        # Extract exception info if provided
        exc_info = kwargs.pop("exc_info", False)

        self._log(logging.ERROR, msg, *args, **kwargs)

        # Log exception info if requested
        if exc_info:
            self.logger.exception("")

    def fatalw(self, msg: str, *args: Any, **kwargs: Any) -> None:
        """Log a fatal message with structured context and terminate the program."""
        if self.use_colors:
            msg = f"{Fore.RED}{Style.BRIGHT}{msg}{Style.RESET_ALL}"

        # Extract exception info if provided
        exc_info = kwargs.pop("exc_info", True)  # Default to True for fatal errors

        self._log(logging.CRITICAL, msg, *args, **kwargs)

        # Log exception info if requested
        if exc_info:
            self.logger.exception("")

        # Terminate the program
        sys.exit(1)

    def with_context(self, **kwargs: Any) -> "ConsoleLogger":
        """Return a new logger with additional persistent context."""
        new_context = self.context.copy()
        new_context.update(kwargs)
        return ConsoleLogger(
            name=self.name, level=self.level, context=new_context, use_colors=self.use_colors
        )

    def with_component(self, component: str) -> "ConsoleLogger":
        """Return a new logger for a specific component."""
        return ConsoleLogger(
            name=f"{self.name}.{component}",
            level=self.level,
            context=self.context.copy(),
            use_colors=self.use_colors,
        )

    def with_node_id(self, node_id: str) -> "ConsoleLogger":
        """Return a new logger with a node ID in its context."""
        new_context = self.context.copy()
        new_context["node_id"] = node_id
        return ConsoleLogger(
            name=self.name, level=self.level, context=new_context, use_colors=self.use_colors
        )
