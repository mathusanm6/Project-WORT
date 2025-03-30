#!/usr/bin/env python3
"""
Main script for Rasptank with MQTT control.
This script initializes all the required components for the Rasptank
to be controlled via MQTT from a PC with a DualSense controller.
"""
import argparse
import os
import signal
import sys
import threading
import time
import uuid
from queue import Empty

from src.common.constants.actions import (
    CAMERA_COMMAND_TOPIC,
    SCAN_COMMAND_TOPIC,
    SHOOT_COMMAND_TOPIC,
)
from src.common.constants.game import FLAG_CAPTURE_DURATION, GAME_EVENT_TOPIC, STATUS_TOPIC
from src.common.constants.movement import MOVEMENT_COMMAND_TOPIC, MOVEMENT_STATE_TOPIC

# Import from src.common
from src.common.constants.server import (
    FLAG_TOPIC,
    INIT_TOPIC,
    QR_TOPIC,
    SHOTIN_TOPIC,
    SHOTOUT_TOPIC,
)
from src.common.logging.decorators import log_function_call
from src.common.logging.logger_api import LogLevel

# Import from logging system
from src.common.logging.logger_factory import LoggerFactory
from src.common.mqtt.client import MQTTClient

# Import from src.rasptank
from src.rasptank.action import ActionController
from src.rasptank.hardware.hardware_main import RasptankHardware
from src.rasptank.movement.controller.mqtt import MQTTMovementController

# Global variables for resources that need cleanup
rasptank_hardware = None
mqtt_client = None
movement_controller = None
action_controller = None
running = True
logger = None

# Global variables for ongoing game
team = None
qr = None
flag = False
hit = 0
capturing = False
tank_id = None
is_currently_on_zone = False


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
    """Handle termination signals gracefully."""
    global running
    logger.infow("Signal received. Stopping gracefully...", "signal", sig)
    running = False


@log_function_call()
def cleanup():
    """Clean up all resources."""
    global mqtt_client, movement_controller, action_controller, rasptank_hardware, team, qr, flag
    team = None
    qr = None
    flag = None

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

    Args:
        client (MQTTClient): MQTT client instance
        topic (str): Topic the message was received on
        payload (str): Message payload
        qos (int): QoS level
        retain (bool): Whether the message was retained
    """
    global qr, tank_id
    try:
        logger.infow("Scan QR code command received", "payload", payload)
        client.publish(QR_TOPIC(tank_id), qr, qos=1)
        client.publish(STATUS_TOPIC, "qr_code_scanning", qos=0)
    except Exception as e:
        logger.errorw("Error handling scan QR command", "error", str(e), exc_info=True)


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
    global rasptank_hardware, mqtt_client, flag, capturing, tank_id, is_currently_on_zone

    # Track whether the tank is currently on the zone
    new_zone_status = rasptank_hardware.is_on_top_of_capture_zone()

    # Only send a message if the status has changed
    if new_zone_status != is_currently_on_zone:
        try:
            if new_zone_status:
                # Just entered the zone
                if mqtt_client and not capturing:
                    mqtt_client.publish(
                        topic=FLAG_TOPIC(tank_id),
                        payload="ENTER_FLAG_AREA",
                        qos=1,
                    )
                    logger.debugw("Published flag area entry event", "tank_id", tank_id)
            else:
                # Just exited the zone
                if mqtt_client:
                    mqtt_client.publish(
                        topic=FLAG_TOPIC(tank_id),
                        payload="EXIT_FLAG_AREA",
                        qos=1,
                    )
                    logger.debugw("Published flag area exit event", "tank_id", tank_id)
        except Exception as e:
            logger.errorw("Failed to publish flag area event", "error", str(e), exc_info=True)

        # Update the status for next comparison
        is_currently_on_zone = new_zone_status


def handle_flag(client, topic, payload, qos, retain):
    global rasptank_hardware, flag, hit, team, qr, capturing
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
    global flag, team, rasptank_hardware
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
    global mqtt_client, running, logger

    if not mqtt_client or not running:
        return

    try:
        # Collect status information
        status = {
            "battery": 85,  # Example battery percentage
            "timestamp": time.time(),
            # Add other status fields as needed
        }

        # Publish status information
        status_message = f"status;{status['battery']};{status['timestamp']}"
        mqtt_client.publish(STATUS_TOPIC, status_message, qos=0)
        logger.debugw(
            "Status published", "battery", status["battery"], "timestamp", status["timestamp"]
        )

        # Schedule next update if still running
        if running:
            threading.Timer(10.0, publish_status_update).start()

    except Exception as e:
        logger.errorw("Error publishing status update", "error", str(e))


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

    return parser.parse_args()


@log_function_call()
def main():
    """Main entry point."""
    global rasptank_hardware, mqtt_client, movement_controller, action_controller, running, logger, tank_id

    # Parse command line arguments
    args = parse_arguments()

    # Configure logging
    logger = create_logger(args.log_level)

    component_logger = logger.with_component("main")
    component_logger.infow("Starting Rasptank main application")

    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Initialize resources
    try:
        # Initialize MQTT Client
        mqtt_logger = logger.with_component("mqtt")
        mqtt_client = MQTTClient(
            mqtt_logger=mqtt_logger,
            broker_address=args.broker,
            broker_port=args.port,
            client_id=args.client_id,
        )

        if not mqtt_client.connect() or not mqtt_client.wait_for_connection(timeout=10):
            mqtt_logger.fatalw("Unable to connect to MQTT broker")
            return 1

        # Initialize Rasptank Hardware
        hw_logger = logger.with_component("hardware")
        rasptank_hardware = RasptankHardware(hw_logger)

        time.sleep(0.2)  # hardware initialization pause

        # Initialize MQTT Movement Controller
        movement_logger = logger.with_component("movement")
        movement_controller = MQTTMovementController(
            movement_logger=movement_logger,
            hardware=rasptank_hardware,
            mqtt_client=mqtt_client,
            command_topic=MOVEMENT_COMMAND_TOPIC,
            state_topic=MOVEMENT_STATE_TOPIC,
        )

        # Initialize Action Controller
        action_logger = logger.with_component("action")
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

        # Server topics communication
        # Set up handler for init server msg
        tank_id = str(uuid.getnode())
        if len(tank_id) > 15:
            tank_id = tank_id[0:15]
        mqtt_client.subscribe(topic=INIT_TOPIC(tank_id), qos=1, callback=handle_init)
        mqtt_client.publish(
            topic="init", payload=f"INIT {tank_id}", qos=1
        )  # Don't change topic, it's should be fixed

        # Set up handler for flag server msg
        mqtt_client.subscribe(topic=FLAG_TOPIC(tank_id), qos=1, callback=handle_flag)

        # Set up handler for qr code management from server
        mqtt_client.subscribe(topic=QR_TOPIC(tank_id), qos=1, callback=handle_qr)
        # Set up handler for shoot server msg
        mqtt_client.subscribe(topic=SHOTIN_TOPIC(tank_id), qos=1, callback=handle_shotin)
        mqtt_client.subscribe(topic=SHOTOUT_TOPIC(tank_id), qos=1, callback=handle_shotout)

        # Periodic status updates
        publish_status_update()

        component_logger.infow("Rasptank initialization complete")

        # Main event loop
        while running:
            # Setup signal handlers (once)
            if int(time.time()) % 2 == 0:
                signal.signal(signal.SIGINT, signal_handler)
                signal.signal(signal.SIGTERM, signal_handler)

            on_flag_area()

            try:
                command = rasptank_hardware.led_command_queue.get(timeout=0.1)
                led_logger = logger.with_component("led")

                if command.startswith("hit:"):
                    # Parse the shooter ID from the command
                    parts = command.split(":", 1)
                    shooter = parts[1] if len(parts) > 1 else "unknown"

                    led_logger.infow("Hit event processed in main loop", "shooter", shooter)
                    rasptank_hardware.led_strip.hit_animation()

                    # Send properly formatted message to server
                    mqtt_client.publish(
                        topic=SHOTIN_TOPIC(tank_id), payload=f"SHOT_BY {shooter}", qos=1
                    )
                    led_logger.debugw("Published shot in event", "shooter", shooter)
                elif command == "hit":
                    # Legacy support for old format without shooter ID
                    led_logger.infow("Hit event processed in main loop (legacy format)")
                    rasptank_hardware.led_strip.hit_animation()

                    # For legacy support, we need to handle this differently
                    # Use a placeholder or notify about missing shooter ID
                    mqtt_client.publish(
                        topic=SHOTIN_TOPIC(tank_id), payload="SHOT_BY unknown", qos=1
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

            time.sleep(0.05)  # 50ms

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
