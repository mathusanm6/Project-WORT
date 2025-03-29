import os
import time
from functools import wraps

from src.common.logging.logger_factory import LoggerFactory

default_logger = LoggerFactory.create_logger(
    logger_type=os.environ.get("RASPTANK_LOGGER_TYPE", "console"),
    name="Rasptank",
    level=os.environ.get("RASPTANK_LOG_LEVEL", "INFO"),
)


def log_function_call(logger=None):
    """
    Decorator to log function calls with arguments and timing information.

    Args:
        logger: Logger to use, defaults to global default_logger
    """

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            # Use provided logger or default
            current_logger = logger or default_logger

            # Get function details
            func_name = func.__name__

            # Skip self for instance methods
            args_str = (
                ", ".join([str(a) for a in args[1:]])
                if len(args) > 0 and hasattr(args[0], func_name)
                else ", ".join([str(a) for a in args])
            )
            kwargs_str = ", ".join([f"{k}={v}" for k, v in kwargs.items()])
            all_args = ", ".join(filter(None, [args_str, kwargs_str]))

            # Log the call
            current_logger.debugw(f"Calling {func_name}({all_args})")

            # Call the function and time it
            start_time = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed = (time.time() - start_time) * 1000  # ms
                current_logger.debugw(f"Completed {func_name} in {elapsed:.2f}ms")
                return result
            except Exception as e:
                elapsed = (time.time() - start_time) * 1000  # ms
                current_logger.errorw(
                    f"Failed {func_name} after {elapsed:.2f}ms", "error", str(e), exc_info=True
                )
                raise

        return wrapper

    return decorator
