import io
import time

import cv2
import numpy as np
from base_camera import BaseCamera
from picamera2 import Picamera2


class Camera(BaseCamera):
    @staticmethod
    def frames():
        with Picamera2() as camera:
            # Configure camera
            config = camera.create_still_configuration(main={"size": (640, 480)})
            camera.configure(config)
            camera.start()

            # Let camera warm up
            print("Warming up camera...")
            time.sleep(2)
            print("Camera ready")

            stream = io.BytesIO()
            try:
                while True:
                    # Capture frame to memory stream
                    camera.capture_file(stream, format="jpeg")
                    stream.seek(0)
                    # Return the frame
                    yield stream.read()

                    # Reset stream for next frame
                    stream.seek(0)
                    stream.truncate()
            finally:
                camera.stop()

    def get_frame(self, fps=None):
        """Return the current camera frame with optional FPS display."""
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
            cv2.putText(img, f"FPS: {fps}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

            # Encode the modified image back to jpeg
            _, jpeg = cv2.imencode(".jpg", img)
            return jpeg.tobytes()
        except Exception as e:
            print(f"Error adding FPS to frame: {e}")
            # Return original frame if there's an error
            return frame_bytes

    def read_qr_code(self):
        """Read QR codes from the current frame."""
        try:
            from pyzbar.pyzbar import decode

            # Get current frame and convert to numpy array
            frame_bytes = super().get_frame()
            nparr = np.frombuffer(frame_bytes, np.uint8)
            img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)

            # Detect and decode QR codes
            decoded_objects = decode(img)
            qr_codes = [obj.data.decode("utf-8") for obj in decoded_objects]
            return qr_codes
        except Exception as e:
            print(f"Error reading QR code: {e}")
            return []
