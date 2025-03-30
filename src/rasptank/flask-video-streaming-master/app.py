#!/usr/bin/env python
import os
import time
from importlib import import_module

from flask import Flask, Response, render_template

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
            print(f"FPS: {fps}")  # Print FPS to the console

        yield b"--frame\r\n"
        yield b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n--frame\r\n"


@app.route("/video_feed")
def video_feed():
    """Video streaming route. Put this in the src attribute of an img tag."""
    return Response(gen(Camera()), mimetype="multipart/x-mixed-replace; boundary=frame")


if __name__ == "__main__":
    app.run(host="0.0.0.0", threaded=True)
