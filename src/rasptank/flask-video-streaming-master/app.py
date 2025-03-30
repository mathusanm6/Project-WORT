#!/usr/bin/env python
import os
import time
from importlib import import_module

from flask import Flask, Response, jsonify, render_template

# Detect the environment (Raspberry Pi or PC)
try:
    # If the `picamera` module is available, assume we are on a Raspberry Pi
    from camera_pi2 import Camera

    print("Using Raspberry Pi camera")
except ImportError:
    # Otherwise, use a PC-compatible camera (e.g., OpenCV)
    from camera import Camera

    print("Using PC camera")

app = Flask(__name__)
camera_instance = None


def get_camera():
    global camera_instance
    if camera_instance is None:
        camera_instance = Camera()
    return camera_instance


@app.route("/")
def index():
    """Video streaming home page."""
    return render_template("index.html")


def gen(camera):
    """Video streaming generator function."""
    prev_time = time.time()
    frame_count = 0
    fps = 0

    while True:
        # Capture a frame with FPS displayed
        frame = camera.get_frame(fps=fps)
        frame_count += 1

        # Calculate elapsed time
        current_time = time.time()
        elapsed_time = current_time - prev_time

        if elapsed_time >= 1.0:  # Update FPS every second
            fps = frame_count
            frame_count = 0
            prev_time = current_time

        yield b"--frame\r\n"
        yield b"Content-Type: image/jpeg\r\n\r\n"
        yield frame
        yield b"\r\n"


@app.route("/video_feed")
def video_feed():
    """Video streaming route. Put this in the src attribute of an img tag."""
    return Response(
        gen(get_camera()),
        mimetype="multipart/x-mixed-replace; boundary=frame",
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


@app.route("/latest_frame")
def latest_frame():
    """Alternative endpoint that returns just the latest frame as JPEG."""
    # Get the latest frame
    frame = get_camera().get_frame()

    # Return as a regular JPEG response
    return Response(frame, mimetype="image/jpeg")


@app.route("/read_qr")
def read_qr():
    """Endpoint to read QR codes from the current frame."""
    camera = get_camera()
    qr_codes = camera.read_qr_code()

    return jsonify({"success": True, "qr_codes": qr_codes, "count": len(qr_codes)})


@app.errorhandler(404)
def page_not_found(e):
    """Redirect to the main page if an invalid route is accessed."""
    return index()


if __name__ == "__main__":
    app.run(host="0.0.0.0", threaded=True)
