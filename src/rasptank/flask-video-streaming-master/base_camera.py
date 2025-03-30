import threading
import time
from typing import Any, Dict, Generator, Iterator, List, Optional

# Handle different ways to get the thread identifier
try:
    from greenlet import getcurrent as get_ident
except ImportError:
    try:
        from thread import get_ident  # type: ignore
    except ImportError:
        from _thread import get_ident  # type: ignore

# Import the Logger API
from src.common.logging.logger_api import Logger
from src.common.logging.logger_factory import LoggerFactory, LogLevel


class CameraEvent:
    """
    An Event-like class that signals all active clients when a new frame is
    available.
    """

    def __init__(self, logger: Optional[Logger] = None):
        """
        Initialize the camera event system.

        Args:
            logger: Logger instance for event-related logging
        """
        self.events: Dict[int, List[Any]] = {}
        # Initialize logger if not provided
        self.logger = logger or LoggerFactory.create_logger(
            logger_type="console", name="CameraEvent", level=LogLevel.INFO, use_colors=True
        )
        self.logger.debugw("Camera event system initialized")

    def wait(self) -> bool:
        """
        Invoked from each client's thread to wait for the next frame.

        Returns:
            True if the wait completed successfully
        """
        ident = get_ident()
        if ident not in self.events:
            # This is a new client
            # Add an entry for it in the self.events dict
            # Each entry has two elements, a threading.Event() and a timestamp
            self.logger.debugw("New client connected", "client_id", ident)
            self.events[ident] = [threading.Event(), time.time()]
        return self.events[ident][0].wait()

    def set(self) -> None:
        """
        Invoked by the camera thread when a new frame is available.
        Removes clients that haven't processed frames for too long.
        """
        now = time.time()
        remove = None
        client_count = 0

        for ident, event in self.events.items():
            if not event[0].is_set():
                # If this client's event is not set, then set it
                # Also update the last set timestamp to now
                event[0].set()
                event[1] = now
                client_count += 1
            else:
                # If the client's event is already set, it means the client
                # did not process a previous frame
                # If the event stays set for more than 5 seconds, then assume
                # the client is gone and remove it
                if now - event[1] > 5:
                    self.logger.infow(
                        "Client timed out", "client_id", ident, "inactive_seconds", now - event[1]
                    )
                    remove = ident

        if remove:
            del self.events[remove]
            self.logger.infow(
                "Removed inactive client",
                "client_id",
                remove,
                "remaining_clients",
                len(self.events),
            )

        # Occasionally log the number of active clients
        if client_count > 0 and int(now) % 30 == 0:  # Log every ~30 seconds
            self.logger.infow("Active clients", "count", len(self.events))

    def clear(self) -> None:
        """
        Invoked from each client's thread after a frame was processed.
        """
        try:
            ident = get_ident()
            if ident in self.events:
                self.events[ident][0].clear()
        except Exception as e:
            self.logger.errorw(
                "Error clearing event", "error", str(e), "client_id", get_ident(), exc_info=True
            )


class BaseCamera:
    """
    Base camera class that handles the background thread for reading frames.
    """

    thread = None  # Background thread that reads frames from camera
    frame = None  # Current frame is stored here by background thread
    last_access = 0  # Time of last client access to the camera
    event = None  # CameraEvent instance
    logger = None  # Logger instance

    def __init__(self):
        """
        Start the background camera thread if it isn't running yet.
        """
        # Initialize class logger if not already done
        if BaseCamera.logger is None:
            BaseCamera.logger = LoggerFactory.create_logger(
                logger_type="console", name="BaseCamera", level=LogLevel.INFO, use_colors=True
            )

        # Initialize event system if not already done
        if BaseCamera.event is None:
            BaseCamera.event = CameraEvent(BaseCamera.logger.with_component("event"))

        if BaseCamera.thread is None:
            BaseCamera.logger.infow("Starting camera background thread")
            BaseCamera.last_access = time.time()

            # Start background frame thread
            BaseCamera.thread = threading.Thread(target=self._thread)
            BaseCamera.thread.daemon = True  # Daemon threads exit when the program does
            BaseCamera.thread.start()

            # Wait until first frame is available
            BaseCamera.logger.infow("Waiting for first frame")
            BaseCamera.event.wait()
            BaseCamera.logger.infow("First frame received, camera is ready")

    def get_frame(self) -> bytes:
        """
        Return the current camera frame.

        Returns:
            bytes: JPEG encoded frame data
        """
        BaseCamera.last_access = time.time()

        # Wait for a signal from the camera thread
        BaseCamera.event.wait()
        BaseCamera.event.clear()

        return BaseCamera.frame

    @staticmethod
    def frames() -> Generator[bytes, None, None]:
        """
        Generator that returns frames from the camera.

        Yields:
            bytes: JPEG encoded frame data

        Raises:
            RuntimeError: Must be implemented by subclasses
        """
        raise RuntimeError("Must be implemented by subclasses.")

    @classmethod
    def _thread(cls) -> None:
        """
        Camera background thread that continuously fetches frames.
        """
        cls.logger.infow("Camera thread started")
        frames_iterator = None
        frame_count = 0
        start_time = time.time()

        try:
            # Get a reference to the frames iterator
            frames_iterator = cls.frames()

            # Process frames
            for frame in frames_iterator:
                BaseCamera.frame = frame
                BaseCamera.event.set()  # Send signal to clients
                frame_count += 1

                # Log stats occasionally
                if frame_count % 100 == 0:
                    elapsed = time.time() - start_time
                    fps = frame_count / elapsed if elapsed > 0 else 0
                    cls.logger.infow(
                        "Camera stats",
                        "frames",
                        frame_count,
                        "uptime",
                        f"{elapsed:.1f}s",
                        "avg_fps",
                        f"{fps:.2f}",
                    )

                # Small sleep to allow other threads to run
                time.sleep(0)

                # If there hasn't been any clients asking for frames in
                # the last 10 seconds then stop the thread
                if time.time() - BaseCamera.last_access > 10:
                    cls.logger.infow(
                        "Stopping camera thread due to inactivity",
                        "idle_time",
                        f"{time.time() - BaseCamera.last_access:.1f}s",
                    )
                    break
        except Exception as e:
            cls.logger.errorw(
                "Error in camera thread", "error", str(e), "frame_count", frame_count, exc_info=True
            )
        finally:
            # Clean up
            if frames_iterator is not None and hasattr(frames_iterator, "close"):
                try:
                    frames_iterator.close()
                except Exception as e:
                    cls.logger.errorw("Error closing frames iterator", "error", str(e))

            cls.logger.infow(
                "Camera thread stopped",
                "total_frames",
                frame_count,
                "run_time",
                f"{time.time() - start_time:.1f}s",
            )
            BaseCamera.thread = None
