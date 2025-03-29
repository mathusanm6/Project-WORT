from typing import Any

from src.common.logging.logger_api import Logger


class NoOpLogger(Logger):
    """
    A logger implementation that does nothing.

    Useful for testing or disabling logging.
    """

    def debugw(self, msg: str, *args: Any, **kwargs: Any) -> None:
        pass

    def infow(self, msg: str, *args: Any, **kwargs: Any) -> None:
        pass

    def warnw(self, msg: str, *args: Any, **kwargs: Any) -> None:
        pass

    def errorw(self, msg: str, *args: Any, **kwargs: Any) -> None:
        pass

    def fatalw(self, msg: str, *args: Any, **kwargs: Any) -> None:
        pass

    def with_context(self, **kwargs: Any) -> "Logger":
        return self

    def with_component(self, component: str) -> "Logger":
        return self

    def with_node_id(self, node_id: str) -> "Logger":
        return self
