import io
import time

import cv2
import numpy as np
from base_camera import BaseCamera
from picamera2 import Picamera2

from src.common.logging.logger_api import Logger
from src.common.logging.logger_factory import LoggerFactory, LogLevel


class Camera(BaseCamera):
    def __init__(self):
        # Create camera-specific logger
        self.logger = LoggerFactory.create_logger(
            logger_type="console", name="Camera", level=LogLevel.INFO, use_colors=True
        )
        # Create component-specific loggers
        self.frames_logger = self.logger.with_component("frames")
        self.processing_logger = self.logger.with_component("processing")
        self.qr_logger = self.logger.with_component("qr")

        self.logger.infow("Camera class initialized")
        super().__init__()

    @staticmethod
    def frames():
        # Since this is a static method, we need to create a logger here
        frames_logger = LoggerFactory.create_logger(
            logger_type="console", name="Camera.frames", level=LogLevel.INFO, use_colors=True
        )

        frames_logger.infow("Starting camera frame capture")
        with Picamera2() as camera:
            # Configure camera
            config = camera.create_still_configuration(main={"size": (640, 480)})
            camera.configure(config)
            camera.start()

            # Let camera warm up
            frames_logger.infow("Warming up camera...")
            time.sleep(2)
            frames_logger.infow("Camera ready")

            stream = io.BytesIO()
            frame_count = 0
            start_time = time.time()

            try:
                while True:
                    # Capture frame to memory stream
                    camera.capture_file(stream, format="jpeg")
                    stream.seek(0)

                    # Log occasional frame statistics
                    frame_count += 1
                    if frame_count % 100 == 0:
                        elapsed = time.time() - start_time
                        fps = frame_count / elapsed if elapsed > 0 else 0
                        frames_logger.infow(
                            "Camera statistics",
                            "frames",
                            frame_count,
                            "elapsed_sec",
                            f"{elapsed:.1f}",
                            "avg_fps",
                            f"{fps:.2f}",
                        )

                    # Return the frame
                    yield stream.read()

                    # Reset stream for next frame
                    stream.seek(0)
                    stream.truncate()
            except Exception as e:
                frames_logger.errorw(
                    "Error in camera frame capture", "error", str(e), exc_info=True
                )
                raise
            finally:
                frames_logger.infow("Stopping camera")
                camera.stop()

    def get_frame(self, fps=None):
        """Return the current camera frame with optional FPS display."""
        try:
            frame_bytes = super().get_frame()

            # If FPS is not required, return the frame as is
            if fps is None:
                return frame_bytes

            # Add FPS info to the frame
            try:
                # Convert jpeg to numpy array
                nparr = np.frombuffer(frame_bytes, np.uint8)
                img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

                # Add FPS text
                cv2.putText(
                    img, f"FPS: {fps}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2
                )

                # Encode the modified image back to jpeg
                _, jpeg = cv2.imencode(".jpg", img)
                return jpeg.tobytes()
            except Exception as e:
                self.processing_logger.errorw(
                    "Error adding FPS to frame", "error", str(e), "fps", fps, exc_info=True
                )
                # Return original frame if there's an error
                return frame_bytes
        except Exception as e:
            self.processing_logger.errorw(
                "Error getting camera frame", "error", str(e), exc_info=True
            )
            # Re-raise to let the caller handle it
            raise

    def read_qr_code(self):
        """Read QR codes from the current frame."""
        try:
            from pyzbar.pyzbar import decode

            # Get current frame and convert to numpy array
            self.qr_logger.debugw("Reading QR code from current frame")
            frame_bytes = super().get_frame()
            nparr = np.frombuffer(frame_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            # Detect and decode QR codes
            start_time = time.time()
            decoded_objects = decode(img)
            elapsed = time.time() - start_time

            qr_codes = [obj.data.decode("utf-8") for obj in decoded_objects]

            # Log the results
            if qr_codes:
                self.qr_logger.infow(
                    "QR codes detected",
                    "count",
                    len(qr_codes),
                    "codes",
                    qr_codes,
                    "decode_time_ms",
                    f"{elapsed*1000:.2f}",
                )
            else:
                self.qr_logger.debugw(
                    "No QR codes detected", "decode_time_ms", f"{elapsed*1000:.2f}"
                )

            return qr_codes
        except ImportError as e:
            self.qr_logger.errorw(
                "Missing required library for QR code reading",
                "error",
                str(e),
                "action",
                "Install with: pip install pyzbar",
            )
            return []
        except Exception as e:
            self.qr_logger.errorw("Error reading QR code", "error", str(e), exc_info=True)
            return []
