import cv2
import numpy as np
from pyzbar.pyzbar import decode


class Camera:
    def __init__(self):
        # Initialize the camera
        self.video = cv2.VideoCapture(0)

    def __del__(self):
        # Release the camera
        self.video.release()

    def get_frame(self, fps=None):
        # Capture a frame from the camera
        success, image = self.video.read()
        if not success:
            return None

        # Detect QR codes in the frame
        decoded_objects = decode(image)
        for obj in decoded_objects:
            # Draw a rectangle around the QR code
            points = obj.polygon
            if len(points) > 4:  # If the QR code is distorted
                hull = cv2.convexHull(np.array([point for point in points], dtype=np.float32))
                points = hull
            points = [(int(point.x), int(point.y)) for point in points]
            for i in range(len(points)):
                cv2.line(image, points[i], points[(i + 1) % len(points)], (0, 255, 0), 2)

            # Add the QR code text above the rectangle
            qr_text = obj.data.decode("utf-8")
            cv2.putText(
                image,
                qr_text,
                (points[0][0], points[0][1] - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0),
                2,
            )

        # Add FPS to the frame if provided
        if fps is not None:
            cv2.putText(image, f"FPS: {fps}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        # Encode the frame as JPEG
        _, jpeg = cv2.imencode(".jpg", image)
        return jpeg.tobytes()

    def read_qr_code(self):
        # Capture a frame from the camera
        success, image = self.video.read()
        if not success:
            return None
        # Detect and decode QR codes
        decoded_objects = decode(image)
        qr_codes = [obj.data.decode("utf-8") for obj in decoded_objects]
        return qr_codes
