#!/usr/bin/env python3
"""
Main script for Rasptank with MQTT control.
This script initializes all the required components for the Rasptank
to be controlled via MQTT from a PC with a DualSense controller.
"""
import argparse
import os
import signal
import subprocess
import sys
import threading
import time
import uuid
from queue import Empty
from threading import current_thread, main_thread

from src.common.camera_client import CameraClient
from src.common.constants.actions import (
    CAMERA_COMMAND_TOPIC,
    SCAN_COMMAND_TOPIC,
    SHOOT_COMMAND_TOPIC,
)
from src.common.constants.game import FLAG_CAPTURE_DURATION, GAME_EVENT_TOPIC, STATUS_TOPIC
from src.common.constants.movement import MOVEMENT_COMMAND_TOPIC, MOVEMENT_STATE_TOPIC

# Import from src.common
from src.common.logging.decorators import log_function_call
from src.common.logging.logger_api import Logger, LogLevel
from src.common.logging.logger_factory import LoggerFactory
from src.common.mqtt.client import MQTTClient

# Import from src.rasptank
from src.rasptank.action import ActionController
from src.rasptank.battery_manager import BatteryManager, PowerSource
from src.rasptank.hardware.hardware_main import RasptankHardware
from src.rasptank.movement.controller.mqtt import MQTTMovementController
from src.rasptank.rasptank_message_factory import RasptankMessageFactory

# Global variables for resources that need cleanup
args = None
logger: Logger = None
battery_manager: BatteryManager = None
rasptank_hardware: RasptankHardware = None
mqtt_client: MQTTClient = None
movement_controller: MQTTMovementController = None
action_controller: ActionController = None
running = True
camera_process = None
camera_client: CameraClient = None
rasptank_message_factory: RasptankMessageFactory = None

# Global variables for ongoing game
team = None
qr = None
flag = False
hit = 0
capturing = False
tank_id = None
is_currently_on_zone = False

TANK_ID = str(uuid.getnode())


# TODO : REMOVE
QR_TOPIC = lambda tank_id: f"rasptank/{tank_id}/qr_code"
FLAG_TOPIC = lambda tank_id: f"rasptank/{tank_id}/flag"
INIT_TOPIC = lambda tank_id: f"rasptank/{tank_id}/init"
SHOTIN_TOPIC = lambda tank_id: f"rasptank/{tank_id}/shots/in"
SHOTOUT_TOPIC = lambda tank_id: f"rasptank/{tank_id}/shots/out"


def create_logger(log_level_str):
    """Create and configure the main logger."""
    global logger

    # Convert string log level to proper LogLevel value
    log_level = LogLevel.INFO
    if log_level_str.upper() == "DEBUG":
        log_level = LogLevel.DEBUG
    elif log_level_str.upper() == "WARNING":
        log_level = LogLevel.WARNING
    elif log_level_str.upper() == "ERROR":
        log_level = LogLevel.ERROR

    # Create the main logger
    logger = LoggerFactory.create_logger(
        logger_type=os.environ.get("RASPTANK_LOGGER_TYPE", "console"),
        name="RasptankMain",
        level=log_level,
        use_colors=True,
    )

    return logger


def signal_handler(sig, frame):
    """Handle termination signals gracefully with timeout enforcement."""
    global running
    logger.infow("Signal received. Stopping gracefully...", "signal", sig)

    # Set global running flag to False
    running = False

    # Check for multiple rapid Ctrl+C presses
    current_time = time.time()
    if not hasattr(signal_handler, "last_signal_time"):
        signal_handler.last_signal_time = 0
        signal_handler.signal_count = 0

    # If another signal was received within 1 second, increment counter
    if current_time - signal_handler.last_signal_time < 1:
        signal_handler.signal_count += 1
    else:
        signal_handler.signal_count = 1

    signal_handler.last_signal_time = current_time

    # If 3 or more signals received rapidly, force exit
    if signal_handler.signal_count >= 3:
        logger.warnw("Multiple interrupt signals received. Forcing immediate exit.")
        os._exit(1)

    # Start a watchdog thread that will force-exit after a timeout
    def force_exit():
        try:
            time.sleep(3)  # Wait 3 seconds for graceful shutdown
            if threading.current_thread() != threading.main_thread():
                logger.errorw("Graceful shutdown timed out after 3 seconds. Forcing exit.")
                os._exit(1)  # Force exit if still running after timeout
        except:
            pass

    # Start the watchdog as daemon thread so it doesn't block program exit
    watchdog = threading.Thread(target=force_exit, daemon=True)
    watchdog.start()

    # If in main thread, try to clean up immediately
    if threading.current_thread() == threading.main_thread():
        try:
            cleanup()
        except Exception as e:
            logger.errorw("Error during immediate cleanup", "error", str(e))
            os._exit(1)


@log_function_call()
def cleanup():
    """Clean up all resources."""
    global camera_client

    # Clean up camera client if initialized
    if camera_client:
        try:
            logger.infow("Cleaning up camera client")
            camera_client.cleanup()
            camera_client = None
        except Exception as e:
            logger.errorw("Camera client cleanup failed", "error", str(e), exc_info=True)

    # Stop camera process if running
    if camera_process:
        try:
            logger.infow("Stopping camera process")
            camera_process.terminate()
            camera_process.wait(timeout=5)
        except Exception as e:
            logger.errorw("Camera process cleanup failed", "error", str(e), exc_info=True)
            # Force kill if terminate fails
            try:
                camera_process.kill()
            except:
                pass

    # Clean up battery manager
    if battery_manager:
        try:
            logger.infow("Stopping battery manager")
            battery_manager.stop()
        except Exception as e:
            logger.errorw("Battery manager cleanup failed", "error", str(e), exc_info=True)

    # Clean up movement controller
    if movement_controller:
        try:
            logger.infow("Cleaning up movement controller")
            movement_controller.stop()
            movement_controller.cleanup()
        except Exception as e:
            logger.errorw("Movement controller cleanup failed", "error", str(e), exc_info=True)

    # Clean up Rasptank hardware (including IR receiver polling)
    if rasptank_hardware:
        try:
            logger.infow("Cleaning up Rasptank hardware")
            rasptank_hardware.cleanup()
        except Exception as e:
            logger.errorw("Rasptank hardware cleanup failed", "error", str(e), exc_info=True)

    # Disconnect MQTT client
    if mqtt_client:
        try:
            logger.infow("Disconnecting MQTT client")
            mqtt_client.disconnect()
        except Exception as e:
            logger.errorw("MQTT client disconnect failed", "error", str(e), exc_info=True)


def initialize_camera_client(camera_server_url=None):
    """Initialize the camera client for QR code scanning.

    Args:
        camera_server_url (str, optional): URL for the camera server.
            If None, uses the local Flask server URL.

    Returns:
        CameraClient: Initialized camera client instance, or None if initialization failed.
    """
    global camera_client

    try:
        camera_client_logger = logger.with_component("camera_client")

        # Use provided URL or construct one from local settings
        if camera_server_url is None:
            # Default to localhost with the camera port from args
            camera_port = getattr(args, "camera_port", 5000)
            camera_server_url = f"http://localhost:{camera_port}"

        camera_client_logger.infow("Initializing camera client", "server_url", camera_server_url)

        # Create camera client instance
        camera_client = CameraClient(
            logger=camera_client_logger,
            server_url=camera_server_url,
            target_fps=10,  # Lower than default 30 to reduce resource usage
            num_fetch_threads=1,  # Just one thread since we only need QR codes occasionally
            timeout=args.qr_scan_timeout if hasattr(args, "qr_scan_timeout") else 1.0,
        )

        # Check connection
        if camera_client._check_connection():
            camera_client_logger.infow("Successfully connected to camera server")
            return camera_client
        else:
            camera_client_logger.warnw(
                "Failed to connect to camera server", "url", camera_server_url
            )
            return None

    except Exception as e:
        camera_client_logger.errorw(
            "Error initializing camera client", "error", str(e), exc_info=True
        )
        return None


def start_camera_server(camera_port=5000, debug_mode=False):
    """
    Start the Flask camera server in a separate process with improved process management.
    """
    global camera_process

    # Create a component-specific logger for this function
    camera_server_logger = logger.with_component("camera_server")
    camera_server_logger.infow(
        "Starting camera server",
        "port",
        camera_port,
        "debug_mode",
        debug_mode,
        "timestamp",
        time.time(),
    )

    # Get the directory of the current script
    current_dir = os.path.dirname(os.path.abspath(__file__))

    # Build the path to app.py
    app_path = os.path.join(current_dir, "flask-video-streaming-master", "app.py")
    camera_server_logger.debugw("Resolved app path", "path", app_path)

    # Check if app.py exists
    if not os.path.exists(app_path):
        camera_server_logger.errorw(
            "Cannot find app.py", "path", app_path, "working_dir", os.getcwd()
        )
        return False

    # Set up environment variables for Flask
    env_vars = {
        **os.environ,
        "FLASK_APP": app_path,
        "FLASK_RUN_PORT": str(camera_port),
        "FLASK_DEBUG": "1" if debug_mode else "0",
        # Pass the logging configuration to the child process
        "CAMERA_LOGGER_TYPE": os.environ.get("RASPTANK_LOGGER_TYPE", "console"),
        "CAMERA_LOG_LEVEL": str(logger.logger.level),  # Convert to string to avoid TypeError
    }

    # Start the Flask server as a subprocess
    try:
        start_time = time.time()
        camera_server_logger.infow("Launching camera server subprocess")

        # Use either preexec_fn OR start_new_session, not both
        if os.name == "posix":  # Linux, macOS, etc.
            camera_process = subprocess.Popen(
                [sys.executable, app_path],
                env=env_vars,
                start_new_session=True,  # This will create a new process group
            )
        else:  # Windows
            camera_process = subprocess.Popen(
                [sys.executable, app_path],
                env=env_vars,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,  # Windows equivalent
            )

        camera_server_logger.infow("Camera server logs will appear in this terminal")

        # Wait a moment to ensure the process starts
        wait_time = 3
        camera_server_logger.debugw("Waiting for server startup", "wait_seconds", wait_time)
        time.sleep(wait_time)

        # Check if process is running
        if camera_process.poll() is not None:
            # Process exited immediately, likely an error
            camera_server_logger.errorw(
                "Camera server failed to start",
                "returncode",
                camera_process.returncode,
                "startup_time",
                f"{time.time() - start_time:.2f}s",
            )
            return False

        # Process health check
        if hasattr(camera_process, "pid") and camera_process.pid:
            camera_server_logger.infow(
                "Camera server started successfully",
                "pid",
                camera_process.pid,
                "startup_time",
                f"{time.time() - start_time:.2f}s",
            )

            # Set up a periodic health check for the camera server
            def health_check():
                try:
                    # Make sure the process is still running and we're still running overall
                    if camera_process and camera_process.poll() is None and running:
                        health_logger = logger.with_component("camera_health")
                        health_logger.debugw(
                            "Camera server health check",
                            "pid",
                            camera_process.pid,
                            "status",
                            "running",
                            "uptime",
                            f"{time.time() - start_time:.1f}s",
                        )

                        # Schedule next check if still running
                        if running:
                            threading.Timer(30.0, health_check).start()
                    else:
                        # Process has died or program is shutting down
                        if running:  # Only log if we're not in shutdown
                            health_logger = logger.with_component("camera_health")
                            health_logger.warnw(
                                "Camera server process died",
                                "pid",
                                camera_process.pid if camera_process else None,
                                "uptime",
                                f"{time.time() - start_time:.1f}s",
                            )
                except Exception as e:
                    logger.errorw("Error in health check", "error", str(e), exc_info=True)

            # Start first health check after 30 seconds
            if running:
                threading.Timer(30.0, health_check).start()

            return True
        else:
            camera_server_logger.errorw(
                "Camera server process exists but has no PID",
                "startup_time",
                f"{time.time() - start_time:.2f}s",
            )
            return False

    except Exception as e:
        camera_server_logger.errorw(
            "Failed to start camera server",
            "error",
            str(e),
            "error_type",
            type(e).__name__,
            exc_info=True,
        )
        return False


@log_function_call()
def handle_shoot_command(client, topic, payload, qos, retain):
    """Handle shoot commands received via MQTT."""
    try:
        logger.debugw("Shoot command received", "payload", payload)

        # Use IRBlast to send the IR signal
        if not action_controller:
            logger.errorw("Action controller not initialized")
            return

        success = action_controller.shoot(verbose=False)

        if success:
            logger.debugw("IR blast successfully sent")
            # Publish confirmation to allow controller feedback
            client.publish(STATUS_TOPIC, "shot_fired", qos=0)
        else:
            logger.errorw("Failed to send IR blast")

    except Exception as e:
        logger.errorw("Error handling shoot command", "error", str(e), exc_info=True)


@log_function_call()
def handle_scan_command(client, topic, payload, qos, retain):
    """Handle scan QR code commands received via MQTT.

    Uses the global camera client to fetch QR codes directly from the camera server.

    Args:
        client (MQTTClient): MQTT client instance
        topic (str): Topic the message was received on
        payload (str): Message payload
        qos (int): QoS level
        retain (bool): Whether the message was retained
    """
    try:
        logger.infow("Scan QR code command received", "payload", payload)

        # Check if camera client is initialized
        if camera_client is None:
            logger.warnw("Camera client not initialized")
            return

        client.publish(QR_TOPIC(TANK_ID), f"QR_CODE {camera_client.read_qr_codes()}", qos=1)
        client.publish(STATUS_TOPIC, "Using stored QR code (camera unavailable)", qos=0)

        # Try to read QR codes from the camera
        logger.infow("Scanning for QR codes using camera client")
        client.publish(STATUS_TOPIC, "Scanning for QR codes...", qos=0)

        # Force refresh to get the latest QR codes
        qr_codes = camera_client.read_qr_codes(force_refresh=True)

        if qr_codes:
            detected_qr = qr_codes[0]  # Use the first detected QR code
            logger.infow("QR code detected via camera", "qr_code", detected_qr)

            # Send the detected QR code to the server
            client.publish(QR_TOPIC(TANK_ID), f"QR_CODE {detected_qr}", qos=1)
            client.publish(STATUS_TOPIC, f"QR code detected: {detected_qr}", qos=0)
        else:
            # If no QR code detected via camera, fall back to the stored QR value
            logger.warnw("No QR code detected via camera, using stored value", "stored_qr", qr)
            client.publish(QR_TOPIC(TANK_ID), f"QR_CODE {qr}", qos=1)
            client.publish(STATUS_TOPIC, "Using stored QR code value", qos=0)

    except Exception as e:
        logger.errorw("Error handling scan QR command", "error", str(e), exc_info=True)

        # Fall back to the stored QR value in case of error
        try:
            client.publish(QR_TOPIC(TANK_ID), f"QR_CODE {qr}", qos=1)
            client.publish(STATUS_TOPIC, "Error scanning QR code, using stored value", qos=0)
        except Exception as fallback_error:
            logger.errorw("Error in fallback QR code handling", "error", str(fallback_error))


def handle_camera_command(client, topic, payload, qos, retain):
    """Handle camera control commands received via MQTT.

    Args:
        client (MQTTClient): MQTT client instance
        topic (str): Topic the message was received on
        payload (str): Message payload (format: "pan;tilt")
        qos (int): QoS level
        retain (bool): Whether the message was retained
    """
    try:
        logger.infow("Camera command received", "payload", payload)

        # Parse pan and tilt values
        parts = payload.split(";")
        if len(parts) >= 2:
            try:
                pan = float(parts[0])
                tilt = float(parts[1])

                # TODO: Implement actual camera servo control
                # This could involve driving servo motors via GPIO/PWM
                logger.infow("Moving camera", "pan", pan, "tilt", tilt)

                # Publish confirmation
                client.publish(STATUS_TOPIC, f"camera_moved;{pan};{tilt}", qos=0)
            except ValueError:
                logger.warnw("Invalid camera command format", "payload", payload)
        else:
            logger.warnw("Invalid camera command format", "payload", payload)

    except Exception as e:
        logger.errorw("Error handling camera command", "error", str(e), exc_info=True)


# Flag capture logic and timer handled by server not rasptank
# On zone logic
def on_flag_area():
    """
    Checks whether the Rasptank is on the capture zone and handles
    the full capture logic (timing, MQTT events, animations).
    """
    global is_currently_on_zone

    # Track whether the tank is currently on the zone
    new_zone_status = rasptank_hardware.is_on_top_of_capture_zone()

    # Only send a message if the status has changed
    if new_zone_status != is_currently_on_zone:
        try:
            if new_zone_status:
                # Just entered the zone
                if mqtt_client and not capturing:
                    mqtt_client.publish(
                        topic=FLAG_TOPIC(TANK_ID),
                        payload="ENTER_FLAG_AREA",
                        qos=1,
                    )
                    logger.debugw("Published flag area entry event", "TANK_ID", TANK_ID)
            else:
                # Just exited the zone
                if mqtt_client:
                    mqtt_client.publish(
                        topic=FLAG_TOPIC(TANK_ID),
                        payload="EXIT_FLAG_AREA",
                        qos=1,
                    )
                    logger.debugw("Published flag area exit event", "TANK_ID", TANK_ID)
        except Exception as e:
            logger.errorw("Failed to publish flag area event", "error", str(e), exc_info=True)

        # Update the status for next comparison
        is_currently_on_zone = new_zone_status


def handle_flag(client, topic, payload, qos, retain):
    global flag, hit, team, qr, capturing
    try:
        # Handle server msg
        msgs = payload.split(" ")
        msg = msgs[0]

        # Check first if it's a frequent status message
        if msg in ["ENTER_FLAG_AREA", "EXIT_FLAG_AREA"]:
            # Log these frequent messages at DEBUG level only
            logger.debugw("Flag area status message", "action", msg)
            # No further processing needed for these messages
            return

        # For all other messages (important ones), log at INFO level
        logger.infow("Flag message received", "topic", topic, "payload", payload)

        if msg == "START_CATCHING":
            capturing = True
            client.publish(STATUS_TOPIC, "Catching flag...", qos=0)
            client.publish(
                topic=GAME_EVENT_TOPIC,
                payload="capturing_flag;captured",
                qos=1,
            )
            logger.infow("Starting flag capture animation")
            rasptank_hardware.led_strip.capturing_animation()
        elif msg == "FLAG_CATCHED":
            flag = True
            capturing = False
            logger.infow("Flag captured, enabling flag possession LED state")
            rasptank_hardware.led_strip.flag_possessed()
        elif msg == "FLAG_LOST":
            flag = False
            logger.infow("Flag lost")
            # Flag not possessed animation ?
        elif msg == "ABORT_CATCHING_SHOT" or msg == "ABORT_CATCHING_EXIT":
            capturing = False
            logger.infow("Flag capture aborted", "reason", msg)
            rasptank_hardware.led_strip.stop_animations()
        elif msg == "ALREADY_GOT" or msg == "NOT_ONBASE":
            client.publish(STATUS_TOPIC, "Cannot catch flag...", qos=0)
            logger.infow("Cannot catch flag", "reason", msg)
        elif msg == "WIN":
            team_winner = msgs[1] if len(msgs) > 1 else "UNKNOWN"
            logger.infow("Game won", "winning_team", team_winner)
            if team_winner == "BLUE":
                client.publish(
                    STATUS_TOPIC, "RAMENEZ LE GREC À LA MAISON, ALLER LES BLEUS ! ALLER !", qos=0
                )
            else:
                client.publish(STATUS_TOPIC, "Meme avec les rouges à trouver", qos=0)
            # Reset game's stats
            hit = 0
            flag = False
            team = None
            qr = None
            capturing = False
            logger.infow("Game stats reset")
        else:
            logger.warnw("Unknown flag message", "topic", topic, "message", msg)
            print(f"Unknown message from server's on topic {topic}, msg= {msg}")
    except Exception as e:
        logger.errorw("Error handling flag command", "error", str(e), exc_info=True)


def handle_init(client, topic, payload, qos, retain):
    global team, qr
    try:
        # Handle server msg
        logger.infow("Initialization message received", "topic", topic, "payload", payload)
        msgs = payload.split(" ")
        if msgs[0] == "TEAM":
            team = msgs[1]
            logger.infow("Team assigned", "team", team)
            client.publish(STATUS_TOPIC, f"We are in team {team}", qos=0)
        elif msgs[0] == "QR_CODE":
            qr = msgs[1]
            logger.infow("QR code received", "qr_code", qr)
            client.publish(STATUS_TOPIC, f"QR code for scan is : {qr}", qos=0)
        elif msgs[0] == "END":
            logger.infow("Initialization complete")
            client.publish(
                STATUS_TOPIC, f"Initialisation from server successful, let's beat some ass", qos=0
            )
        else:
            logger.warnw("Unknown initialization message", "topic", topic, "message", msgs)
            print(f"Unknown message from server's on topic {topic}, msg= {msgs}")

    except Exception as e:
        logger.errorw("Error handling init command", "error", str(e), exc_info=True)


def handle_shotin(client, topic, payload, qos, retain):
    try:
        # Handle server msg
        logger.infow("Shot-in message received", "topic", topic, "payload", payload)
        msg = payload
        if msg == "SHOT":
            logger.infow("Tank was shot, implementing freeze behavior")
            print("TODO freeze the tank")
            # TODO: Implement tank freeze behavior here
        else:
            logger.warnw("Unknown shot-in message", "topic", topic, "message", msg)
            print(f"Unknown message from server's on topic {topic}, msg= {msg}")
    except Exception as e:
        logger.errorw("Error handling shot-in command", "error", str(e), exc_info=True)


def handle_shotout(client, topic, payload, qos, retain):
    global hit
    try:
        # Handle server msg
        logger.infow("Shot-out message received", "topic", topic, "payload", payload)
        msg = payload
        if msg == "FRIENDLY_FIRE":
            logger.warnw("Friendly fire detected")
            print("TODO stop shooting on friend bro you're stupid")
            # TODO: Implement friendly fire warning
        elif msg == "SHOT":
            hit = hit + 1
            logger.infow("Successful hit registered", "total_hits", hit)
            print("TODO headshot")
            # TODO: Implement hit success feedback
        else:
            logger.warnw("Unknown shot-out message", "topic", topic, "message", msg)
            print(f"Unknown message from server's on topic {topic}, msg= {msg}")
    except Exception as e:
        logger.errorw("Error handling shot-out command", "error", str(e), exc_info=True)


def handle_qr(client, topic, payload, qos, retain):
    try:
        logger.infow("QR code scan result received", "topic", topic, "payload", payload)
        msg = payload
        if msg in ["SCAN_SUCCESSFUL", "SCAN_FAILED", "FLAG_DEPOSITED", "NO_FLAG"]:
            client.publish(STATUS_TOPIC, msg, qos=0)
            logger.infow("QR scan result", "result", msg)
            if msg == "FLAG_DEPOSITED":
                logger.infow("Flag successfully deposited, playing scored animation")
                rasptank_hardware.led_strip.scored_animation()
        else:
            logger.warnw("Unknown QR scan message", "topic", topic, "message", msg)
            print(f"Unknown message from server's on topic {topic}, msg= {msg}")
    except Exception as e:
        logger.errorw("Error handling QR scan result", "error", str(e), exc_info=True)


def publish_status_update():
    """Publish periodic status updates."""
    if not mqtt_client or not running:
        return

    try:
        # Get battery percentage from battery manager
        battery_percent = 100  # Default if no battery manager
        power_source = "wired"

        if battery_manager:
            battery_percent = round(battery_manager.get_battery_percentage(), 2)
            power_source = battery_manager.power_source.value

        # Collect status information
        status = {
            "battery": battery_percent,
            "power_source": power_source,
            "timestamp": time.time(),
            # Add other status fields as needed
        }

        # Add camera status
        if camera_process:
            status["camera_running"] = camera_process.poll() is None

        # Add camera client status
        if camera_client:
            status["camera_client_connected"] = camera_client.connected

        # Publish status information
        status_message = (
            f"status;{status['battery']};{status['power_source']};{status['timestamp']}"
        )
        mqtt_client.publish(STATUS_TOPIC, status_message, qos=0)
        logger.infow(
            "Status published",
            "battery",
            status["battery"],
            "power_source",
            status["power_source"],
            "camera",
            status.get("camera_running", False),
            "camera_client",
            status.get("camera_client_connected", False),
            "timestamp",
            status["timestamp"],
        )

        # Schedule next update if still running
        if running:
            threading.Timer(5.0, publish_status_update).start()

    except Exception as e:
        logger.errorw("Error publishing status update", "error", str(e))


def setup_server_subscriptions():
    """Set up MQTT subscriptions for server communication."""
    global TANK_ID

    # Initialize Rasptank message factory
    rasptank_message_factory = RasptankMessageFactory()

    # Server topics communication
    # Set up handler for init server msg
    if len(TANK_ID) > 15:
        TANK_ID = TANK_ID[0:15]
    mqtt_client.subscribe(topic=INIT_TOPIC(TANK_ID), qos=1, callback=handle_init)
    mqtt_client.publish(
        topic="init", payload=f"INIT {TANK_ID}", qos=1
    )  # Don't change topic, it's should be fixed

    # Set up handler for flag server msg
    mqtt_client.subscribe(topic=FLAG_TOPIC(TANK_ID), qos=1, callback=handle_flag)

    # Set up handler for qr code management from server
    mqtt_client.subscribe(topic=QR_TOPIC(TANK_ID), qos=1, callback=handle_qr)
    # Set up handler for shoot server msg
    mqtt_client.subscribe(topic=SHOTIN_TOPIC(TANK_ID), qos=1, callback=handle_shotin)
    mqtt_client.subscribe(topic=SHOTOUT_TOPIC(TANK_ID), qos=1, callback=handle_shotout)


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Rasptank MQTT Control")

    parser.add_argument("--broker", type=str, default="192.168.1.200", help="MQTT broker address")

    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")

    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )

    parser.add_argument("--client-id", type=str, default="rasptank", help="MQTT client ID")

    parser.add_argument(
        "--reset-battery", action="store_true", help="Reset battery to full charge (100%)"
    )

    # Add camera-related arguments
    parser.add_argument("--camera", action="store_true", help="Enable camera functionality")

    parser.add_argument(
        "--camera-port", type=int, default=5000, help="Port for the camera web server"
    )

    parser.add_argument(
        "--camera-url",
        type=str,
        default=None,
        help="URL for the camera server (overrides --camera-port if provided)",
    )

    parser.add_argument(
        "--qr-scan-timeout",
        type=float,
        default=1.0,
        help="Timeout in seconds for QR code scanning requests",
    )

    parser.add_argument(
        "--power-source",
        type=str,
        choices=["battery", "wired"],
        default="wired",
        help="Power source for the Rasptank: 'battery' or 'wired'",
    )

    return parser.parse_args()


@log_function_call()
def main():
    """Main entry point."""
    global rasptank_hardware, mqtt_client, movement_controller, action_controller
    global logger, battery_manager, tank_id, args, camera_client, rasptank_message_factory

    # Parse command line arguments
    args = parse_arguments()

    # Configure logging
    logger = create_logger(args.log_level)

    component_logger = logger.with_component("main")
    component_logger.infow("Starting Rasptank main application")

    camera_logger = component_logger.with_component("camera")

    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Initialize resources
    try:
        # Start camera server if enabled
        camera_server_started = False
        if args.camera:
            camera_server_started = start_camera_server(args.camera_port)
            if not camera_server_started:
                camera_logger.warnw(
                    "Failed to start camera server, continuing without camera functionality"
                )

        # Initialize Camera Client
        if args.camera:
            # Determine camera URL to use
            camera_url = args.camera_url
            if not camera_url and camera_server_started:
                # If a local camera server was started, use it
                camera_url = f"http://localhost:{args.camera_port}"

            # Initialize the camera client if URL is available
            if camera_url:
                # Allow a moment for the camera server to start
                if camera_server_started:
                    time.sleep(1)

                camera_client = initialize_camera_client(camera_url)
                if camera_client:
                    camera_logger.infow("Camera client initialized successfully", "url", camera_url)
                else:
                    camera_logger.warnw(
                        "Failed to initialize camera client, QR code scanning may not work properly"
                    )

        # Initialize MQTT Client
        mqtt_logger = component_logger.with_component("mqtt")
        mqtt_client = MQTTClient(
            mqtt_logger=mqtt_logger,
            broker_address=args.broker,
            broker_port=args.port,
            client_id=args.client_id,
        )

        if not mqtt_client.connect() or not mqtt_client.wait_for_connection(timeout=10):
            mqtt_logger.fatalw("Unable to connect to MQTT broker")
            return 1

        # Initialize Battery Manager (add after other initializations)
        battery_logger = component_logger.with_component("battery")
        battery_manager = BatteryManager(battery_logger)

        if args.reset_battery:
            logger.infow("Resetting battery to full charge (100%)")
            battery_manager.reset_battery()

        # Prompt user for power source
        power_source = PowerSource.BATTERY if args.power_source == "battery" else PowerSource.WIRED
        battery_manager.set_power_source(power_source)

        # Start battery manager
        battery_manager.start()

        # Initialize Rasptank Hardware
        hw_logger = component_logger.with_component("hardware")
        rasptank_hardware = RasptankHardware(hw_logger)

        time.sleep(0.2)  # hardware initialization pause

        # Initialize MQTT Movement Controller
        movement_logger = component_logger.with_component("movement")
        movement_controller = MQTTMovementController(
            movement_logger=movement_logger,
            hardware=rasptank_hardware,
            mqtt_client=mqtt_client,
            command_topic=MOVEMENT_COMMAND_TOPIC,
            state_topic=MOVEMENT_STATE_TOPIC,
        )

        # Initialize Action Controller
        action_logger = component_logger.with_component("action")
        action_controller = ActionController(action_logger, rasptank_hardware)

        # IR Receiver setup
        if not rasptank_hardware.ir_receiver.setup_ir_receiver(
            client=mqtt_client, led_command_queue=rasptank_hardware.get_led_command_queue()
        ):
            return 1

        time.sleep(0.2)

        # MQTT Subscriptions
        mqtt_logger.debugw(
            "Setting up MQTT subscriptions",
            "topics",
            f"{SHOOT_COMMAND_TOPIC}",
        )
        mqtt_client.subscribe(SHOOT_COMMAND_TOPIC, qos=0, callback=handle_shoot_command)
        mqtt_client.subscribe(CAMERA_COMMAND_TOPIC, qos=0, callback=handle_camera_command)
        mqtt_client.subscribe(SCAN_COMMAND_TOPIC, qos=0, callback=handle_scan_command)

        setup_server_subscriptions(
            mqtt_client,
            handle_flag,
            handle_init,
            handle_shotin,
            handle_shotout,
            handle_qr,
        )

        # Periodic status updates
        publish_status_update()

        component_logger.infow("Rasptank initialization complete")

        # Main event loop
        shutdown_requested = False
        shutdown_start_time = None
        main_loop_iterations = 0

        component_logger.infow("Rasptank initialization complete")
        component_logger.infow("Press Ctrl+C to exit")

        while running:
            main_loop_iterations += 1

            # Setup signal handlers (once per second)
            if main_loop_iterations % 20 == 0:  # Assuming 50ms sleep, this is once per second
                signal.signal(signal.SIGINT, signal_handler)
                signal.signal(signal.SIGTERM, signal_handler)

            # If shutdown was requested, track how long it's taking
            if not running and not shutdown_requested:
                shutdown_requested = True
                shutdown_start_time = time.time()
                component_logger.infow("Shutdown requested, finishing current operations...")

            # If shutdown is taking too long, force exit
            if shutdown_requested and time.time() - shutdown_start_time > 5:
                component_logger.warnw(
                    "Shutdown taking too long, forcing exit",
                    "shutdown_duration",
                    f"{time.time() - shutdown_start_time:.1f}s",
                )
                break

            # Call the flag capture logic
            on_flag_area()

            # Check camera process health if enabled (but not during shutdown)
            if (
                not shutdown_requested
                and args.camera
                and camera_process
                and camera_process.poll() is not None
            ):
                # Camera process has died, log the error
                try:
                    stdout, stderr = camera_process.communicate(timeout=1)
                    component_logger.errorw(
                        "Camera process died unexpectedly",
                        "returncode",
                        camera_process.returncode,
                        "stdout",
                        stdout.decode("utf-8", errors="ignore") if stdout else "",
                        "stderr",
                        stderr.decode("utf-8", errors="ignore") if stderr else "",
                    )
                except:
                    component_logger.errorw(
                        "Camera process died unexpectedly", "returncode", camera_process.returncode
                    )

                # Attempt to restart (but not during shutdown)
                if not shutdown_requested and start_camera_server(args.camera_port):
                    component_logger.infow("Camera process successfully restarted")

                    # Also reconnect camera client if it was being used
                    if camera_client:
                        # Try to clean up the old client first
                        try:
                            camera_client.cleanup()
                        except:
                            pass

                        # Reinitialize the camera client
                        time.sleep(1)  # Wait a moment for the server to start
                        camera_client = initialize_camera_client(
                            f"http://localhost:{args.camera_port}"
                        )
                        if camera_client:
                            component_logger.infow("Camera client successfully reconnected")
                        else:
                            component_logger.warnw("Failed to reconnect camera client")

            try:
                command = rasptank_hardware.led_command_queue.get(timeout=0.1)
                led_logger = logger.with_component("led")

                if command == "hit":
                    # Legacy support for old format without shooter ID
                    led_logger.infow("Hit event processed in main loop (legacy format)")
                    rasptank_hardware.led_strip.hit_animation()

                    # For legacy support, we need to handle this differently
                    # Use a placeholder or notify about missing shooter ID
                    mqtt_client.publish(
                        topic=SHOTIN_TOPIC(TANK_ID), payload="SHOT_BY unknown", qos=1
                    )
                    led_logger.warnw(
                        "Published shot in event with unknown shooter - update IR receiver code"
                    )
                else:
                    led_logger.warnw("Unknown command in LED queue", "command", command)
            except Empty:
                pass  # Normal condition, no commands in queue
            except Exception as e:
                component_logger.errorw("Error in main loop", "error", str(e), exc_info=True)

            # Short sleep to prevent CPU hogging, shorter during shutdown
            time.sleep(
                0.05 if not shutdown_requested else 0.01
            )  # 50ms normal, 10ms during shutdown

    except KeyboardInterrupt:
        component_logger.infow("KeyboardInterrupt detected, exiting...")
    except Exception as e:
        component_logger.errorw("Unexpected error in main loop", "error", str(e), exc_info=True)
        return 1
    finally:
        component_logger.infow("Commencing cleanup...")
        cleanup()

    component_logger.infow("Rasptank shutdown complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
