#!/usr/bin/env python
import logging
import os
import sys
import time
import traceback
from importlib import import_module

from flask import Flask, Response, current_app, g, jsonify, render_template, request

# Import logging system components
from src.common.logging.logger_api import Logger, LogLevel
from src.common.logging.logger_factory import LoggerFactory

# Create the main logger for the app
logger = LoggerFactory.create_logger(
    logger_type=os.environ.get("CAMERA_LOGGER_TYPE", "console"),
    name="CameraApp",
    level=LogLevel.INFO if os.environ.get("FLASK_DEBUG", "0") == "0" else LogLevel.DEBUG,
    use_colors=True,
)

# Create component-specific loggers
http_logger = logger.with_component("http")
camera_logger = logger.with_component("camera")
stream_logger = logger.with_component("stream")

# Detect the environment (Raspberry Pi or PC)
camera_module = None
try:
    # First try with Picamera2 (newer Raspberry Pi camera interface)
    from picamera2 import Picamera2

    camera_logger.infow("Picamera2 found - using Raspberry Pi camera with Picamera2")
    from camera_pi2 import Camera

    camera_module = "picamera2"
except ImportError:
    try:
        # Then try with the older picamera module
        import picamera

        camera_logger.infow("PiCamera found - using Raspberry Pi camera with PiCamera")
        from camera_pi import Camera

        camera_module = "picamera"
    except ImportError:
        # Otherwise, use a PC-compatible camera (e.g., OpenCV)
        try:
            camera_logger.infow("No Pi camera modules found - using PC camera")
            from camera import Camera

            camera_module = "opencv"
        except ImportError:
            camera_logger.fatalw(
                "No camera modules could be imported",
                "error",
                "Make sure either picamera, picamera2, or OpenCV is installed",
            )
            # Logger.fatalw will automatically exit the program with status 1

app = Flask(__name__)
camera_instance = None

# Configure Flask's internal logging
# Disable Werkzeug's default logger
werkzeug_logger = logging.getLogger("werkzeug")
werkzeug_logger.setLevel(logging.ERROR)  # Only show errors, not routine requests

# Configure the Flask logger
flask_logger = logging.getLogger("flask.app")
flask_logger.setLevel(logging.INFO)

# Add our logger's handlers to Flask's logger
app.logger.handlers = []
for handler in logger.logger.handlers:
    app.logger.addHandler(handler)
app.logger.setLevel(logger.logger.level)


# Create a request filter to only log interesting requests
class RequestFilter:
    def __init__(self):
        self.last_log_time = 0
        self.request_counts = {}
        self.log_interval = 60  # Log stats every 60 seconds

    def should_log(self, request, response_code):
        """Determine if this request should be logged based on our filtering rules"""
        # Always log non-200 responses
        if response_code != 200:
            return True

        # Always log requests that aren't to our high-volume endpoints
        if not request.path.startswith("/latest_frame") and not request.path.startswith(
            "/video_feed"
        ):
            return True

        # For high-volume endpoints, track counts and log periodically
        current_time = time.time()
        endpoint = request.path.split("?")[0]  # Remove query params

        # Initialize counter for this endpoint if needed
        if endpoint not in self.request_counts:
            self.request_counts[endpoint] = 0

        # Increment counter
        self.request_counts[endpoint] += 1

        # Check if it's time to log stats
        if current_time - self.last_log_time >= self.log_interval:
            # It's time to log the stats for all endpoints
            self.last_log_time = current_time
            return "stats"

        return False


request_filter = RequestFilter()


# Add our custom request logging
@app.after_request
def log_request(response):
    """Custom request logger with filtering for high-volume endpoints"""
    # Check if we should log this request
    log_decision = request_filter.should_log(request, response.status_code)

    if log_decision == "stats":
        # Log periodic stats for high-volume endpoints
        http_logger.infow(
            "Request statistics for high-volume endpoints",
            **{
                f"count_{endpoint}": count
                for endpoint, count in request_filter.request_counts.items()
            },
        )
        # Reset counters
        request_filter.request_counts = {}
    elif log_decision:
        # Log individual request
        http_logger.infow(
            "Request processed",
            "method",
            request.method,
            "path",
            request.path,
            "status",
            response.status_code,
            "size",
            response.content_length,
            "remote_addr",
            request.remote_addr,
        )

    return response


# Add a health check endpoint
@app.route("/health")
def health_check():
    """Health check endpoint to verify the server is running."""
    http_logger.debugw(
        "Health check requested",
        "remote_addr",
        request.remote_addr,
        "user_agent",
        request.user_agent.string,
    )
    return jsonify(
        {
            "status": "ok",
            "camera": "initialized" if camera_instance else "not initialized",
            "camera_module": camera_module,
            "timestamp": time.time(),
        }
    )


def get_camera():
    global camera_instance
    if camera_instance is None:
        try:
            camera_logger.infow("Initializing camera")
            camera_instance = Camera()
            camera_logger.infow("Camera initialized successfully")
        except Exception as e:
            camera_logger.errorw("Error initializing camera", "error", str(e), exc_info=True)
            raise
    return camera_instance


@app.route("/")
def index():
    """Video streaming home page."""
    http_logger.infow("Home page accessed", "remote_addr", request.remote_addr)
    return render_template("index.html")


def gen(camera, client_ip=None, stream_id=None):
    """
    Video streaming generator function.

    Args:
        camera: Camera instance to get frames from
        client_ip: IP address of the client (passed from the route)
        stream_id: Optional unique identifier for the stream
    """
    # If no stream_id provided, generate one
    if stream_id is None:
        stream_id = id(camera)

    # Create a logger for this specific stream
    stream_instance_logger = stream_logger.with_context(stream_id=stream_id, client_ip=client_ip)

    stream_instance_logger.infow("Starting new video stream")

    prev_time = time.time()
    frame_count = 0
    fps = 0
    total_frames = 0
    stream_start_time = time.time()

    try:
        while True:
            frame_start = time.time()

            # Capture a frame with FPS displayed
            frame = camera.get_frame(fps=fps)
            if frame is None:
                stream_instance_logger.warnw("Empty frame received from camera")
                time.sleep(0.1)
                continue

            frame_count += 1
            total_frames += 1

            # Calculate elapsed time
            current_time = time.time()
            elapsed_time = current_time - prev_time
            frame_time = current_time - frame_start

            # Log occasional statistics
            if total_frames % 100 == 0:
                total_elapsed = current_time - stream_start_time
                avg_fps = total_frames / total_elapsed if total_elapsed > 0 else 0
                stream_instance_logger.infow(
                    "Stream statistics",
                    "total_frames",
                    total_frames,
                    "current_fps",
                    fps,
                    "avg_fps",
                    f"{avg_fps:.2f}",
                    "stream_duration",
                    f"{total_elapsed:.1f}s",
                    "frame_processing_time",
                    f"{frame_time*1000:.2f}ms",
                )

            if elapsed_time >= 1.0:  # Update FPS every second
                fps = frame_count
                frame_count = 0
                prev_time = current_time

            yield b"--frame\r\n"
            yield b"Content-Type: image/jpeg\r\n\r\n"
            yield frame
            yield b"\r\n"

    except GeneratorExit:
        # This is the normal way a generator is closed when the client disconnects
        stream_instance_logger.infow(
            "Stream closed by client",
            "total_frames",
            total_frames,
            "duration",
            f"{time.time() - stream_start_time:.1f}s",
        )
    except Exception as e:
        stream_instance_logger.errorw(
            "Error in video streaming generator",
            "error",
            str(e),
            "total_frames",
            total_frames,
            exc_info=True,
        )
        yield b"--frame\r\n"
        yield b"Content-Type: text/plain\r\n\r\n"
        yield f"Error: {str(e)}".encode("utf-8")
        yield b"\r\n"


@app.route("/video_feed")
def video_feed():
    """Video streaming route. Put this in the src attribute of an img tag."""
    http_logger.infow("Video feed requested", "remote_addr", request.remote_addr)

    try:
        # Important: Capture client IP here in the request context
        client_ip = request.remote_addr
        stream_id = f"stream_{time.time()}"

        camera = get_camera()
        return Response(
            gen(camera, client_ip=client_ip, stream_id=stream_id),
            mimetype="multipart/x-mixed-replace; boundary=frame",
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )
    except Exception as e:
        http_logger.errorw(
            "Error in video_feed endpoint",
            "error",
            str(e),
            "remote_addr",
            request.remote_addr,
            exc_info=True,
        )
        return Response(f"Camera error: {str(e)}", status=500, mimetype="text/plain")


@app.route("/latest_frame")
def latest_frame():
    """Alternative endpoint that returns just the latest frame as JPEG."""
    try:
        # Get the latest frame
        frame = get_camera().get_frame()
        if frame is None:
            http_logger.warnw(
                "No frame available for /latest_frame request", "remote_addr", request.remote_addr
            )
            return Response("No frame available", status=503, mimetype="text/plain")

        # Return as a regular JPEG response
        return Response(frame, mimetype="image/jpeg")
    except Exception as e:
        http_logger.errorw(
            "Error in latest_frame endpoint",
            "error",
            str(e),
            "remote_addr",
            request.remote_addr,
            exc_info=True,
        )
        return Response(f"Camera error: {str(e)}", status=500, mimetype="text/plain")


@app.route("/read_qr")
def read_qr():
    """Endpoint to read QR codes from the current frame."""
    http_logger.infow("QR code read requested", "remote_addr", request.remote_addr)

    try:
        camera = get_camera()
        start_time = time.time()
        qr_codes = camera.read_qr_code()
        elapsed = time.time() - start_time

        http_logger.infow(
            "QR code read completed",
            "count",
            len(qr_codes),
            "processing_time",
            f"{elapsed*1000:.2f}ms",
        )
        return jsonify(
            {
                "success": True,
                "qr_codes": qr_codes,
                "count": len(qr_codes),
                "processing_time_ms": round(elapsed * 1000, 2),
            }
        )
    except Exception as e:
        http_logger.errorw(
            "Error in read_qr endpoint",
            "error",
            str(e),
            "remote_addr",
            request.remote_addr,
            exc_info=True,
        )
        return jsonify({"success": False, "error": str(e)})


@app.errorhandler(404)
def page_not_found(e):
    """Redirect to the main page if an invalid route is accessed."""
    http_logger.warnw("404 error", "path", request.path, "remote_addr", request.remote_addr)
    return index()


@app.errorhandler(500)
def server_error(e):
    """Log server errors."""
    http_logger.errorw(
        "500 server error",
        "path",
        request.path,
        "remote_addr",
        request.remote_addr,
        "error",
        str(e),
        exc_info=True,
    )
    return Response("Server error", status=500)


if __name__ == "__main__":
    # Log startup information
    logger.infow("Starting Flask camera server")
    logger.infow(
        "Environment",
        "python_version",
        sys.version,
        "working_directory",
        os.getcwd(),
        "camera_module",
        camera_module,
    )

    # Check for camera modules
    try:
        camera = get_camera()
        logger.infow("Camera initialized successfully in main")
    except Exception as e:
        logger.warnw(
            "Failed to initialize camera",
            "error",
            str(e),
            "message",
            "The server will start, but camera functionality may not work",
        )

    debug_mode = os.environ.get("FLASK_DEBUG", "0") == "1"
    logger.infow("Flask configuration", "debug_mode", debug_mode)

    # Try to get a specific host from environment
    host = os.environ.get("FLASK_RUN_HOST", "0.0.0.0")
    port = int(os.environ.get("FLASK_RUN_PORT", "5000"))

    logger.infow("Starting server", "host", host, "port", port)

    try:
        app.run(host=host, port=port, debug=debug_mode, threaded=True)
    except Exception as e:
        logger.fatalw(
            "Failed to start web server", "error", str(e), "host", host, "port", port, exc_info=True
        )
