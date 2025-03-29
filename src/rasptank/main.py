#!/usr/bin/env python3
"""
Main script for Rasptank with MQTT control.
This script initializes all the required components for the Rasptank
to be controlled via MQTT from a PC with a DualSense controller.
"""

import argparse
import logging
import signal
import sys
import threading
import time
import uuid

from queue import Empty

# Import from src.common
from src.common.constants.actions import SCAN_COMMAND_TOPIC, SHOOT_COMMAND_TOPIC
from src.common.constants.game import GAME_EVENT_TOPIC, STATUS_TOPIC
from src.common.constants.movement import MOVEMENT_COMMAND_TOPIC, MOVEMENT_STATE_TOPIC
from src.common.mqtt.client import MQTTClient
from src.common.mqtt.topics import (
    FLAG_TOPIC,
    INIT_TOPIC,
    MOVEMENT_COMMAND_TOPIC,
    MOVEMENT_STATE_TOPIC,
    QR_TOPIC,
    SHOTIN_TOPIC,
    SHOTOUT_TOPIC,
)

# from src.rasptank.movement.controller.mqtt import MQTTMovementController
# from src.rasptank.movement.movement_factory import MovementControllerType, MovementFactory

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("RasptankMain")

# Global variables for resources that need cleanup
mqtt_client = None
movement_controller = None
shoot_controller = None
camera_controller = None
running = True

# Global variables for ongoing game
team = None
qr = None
flag = False
hit = 0
capturing = False
tank_id = None


def signal_handler(sig, frame):
    """Handle termination signals gracefully."""
    global running
    logger.info("Termination signal received, shutting down...")
    running = False


def cleanup():
    """Clean up all resources."""
    global mqtt_client, movement_controller, shoot_controller, camera_controller, team, qr, flag
    team = None
    qr = None
    flag = None
    # Clean up movement controller
    if movement_controller:
        try:
            logger.info("Cleaning up movement controller")
            movement_controller.stop()
            movement_controller.cleanup()
        except Exception as e:
            logger.error(f"Error cleaning up movement controller: {e}")

    # Clean up shoot controller if exists
    if shoot_controller:
        try:
            logger.info("Cleaning up shoot controller")
            # Implementation depends on your shoot controller class
            pass
        except Exception as e:
            logger.error(f"Error cleaning up shoot controller: {e}")

    # Clean up camera controller if exists
    if camera_controller:
        try:
            logger.info("Cleaning up camera controller")
            # Implementation depends on your camera controller class
            pass
        except Exception as e:
            logger.error(f"Error cleaning up camera controller: {e}")

    # Clean up MQTT client
    if mqtt_client:
        try:
            logger.info("Disconnecting MQTT client")
            mqtt_client.disconnect()
        except Exception as e:
            logger.error(f"Error disconnecting MQTT client: {e}")


def handle_shoot_command(client, topic, payload, qos, retain):
    """Handle shoot commands received via MQTT.

    Args:
        client (MQTTClient): MQTT client instance
        topic (str): Topic the message was received on
        payload (str): Message payload
        qos (int): QoS level
        retain (bool): Whether the message was retained
    """
    try:
        logger.info(f"Shoot command received: {payload}")

        # Parse power level if provided
        power = 100
        if payload and payload.strip():
            try:
                power = float(payload)
            except ValueError:
                pass

        # TODO: Implement actual IR shooting mechanism
        # This could involve triggering an IR LED through GPIO
        logger.info(f"Shooting with power level: {power}")

        # Publish confirmation
        client.publish(STATUS_TOPIC, f"shot_fired;{power}", qos=0)

    except Exception as e:
        logger.error(f"Error handling shoot command: {e}")


def handle_scan_command(client, topic, payload, qos, retain):
    """Handle shoot commands received via MQTT.

    Args:
        client (MQTTClient): MQTT client instance
        topic (str): Topic the message was received on
        payload (str): Message payload
        qos (int): QoS level
        retain (bool): Whether the message was retained
    """
    global qr, tank_id
    try:
        logger.info(f"Scan qr code command received: {payload}")
        client.publish(QR_TOPIC(tank_id), qr, qos=1)
        client.publish(STATUS_TOPIC, "Scan qr code started...", qos=0)
    except Exception as e:
        logger.error(f"Error handling shoot command: {e}")


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
        logger.info(f"Camera command received: {payload}")

        # Parse pan and tilt values
        parts = payload.split(";")
        if len(parts) >= 2:
            try:
                pan = float(parts[0])
                tilt = float(parts[1])

                # TODO: Implement actual camera servo control
                # This could involve driving servo motors via GPIO/PWM
                logger.info(f"Moving camera to pan={pan}, tilt={tilt}")

                # Publish confirmation
                client.publish(STATUS_TOPIC, f"camera_moved;{pan};{tilt}", qos=0)
            except ValueError:
                logger.warning(f"Invalid camera command format: {payload}")
        else:
            logger.warning(f"Invalid camera command format: {payload}")

    except Exception as e:
        logger.error(f"Error handling camera command: {e}")


# Flag capture logic and timer handled by server not rasptank
# On zone logic
def on_flag_area():
    """
    Checks whether the Rasptank is on the capture zone and handles
    the full capture logic (timing, MQTT events, animations).
    """
    global rasptank_hardware, mqtt_client, flag, capturing, tank_id

    # Track whether the tank is currently on the zone
    is_on_zone = rasptank_hardware.is_on_top_of_capture_zone()

    try:
        if is_on_zone:
            if (
                not capturing
            ):  # and not flag: to avoid sending again but server can send us already_got
                # Just entered the zone
                if mqtt_client:
                    mqtt_client.publish(
                        topic=FLAG_TOPIC(tank_id),
                        payload="ENTER_FLAG_AREA",
                        qos=1,
                    )
        else:
            if mqtt_client:
                mqtt_client.publish(
                    topic=FLAG_TOPIC(tank_id),
                    payload="EXIT_FLAG_AREA",
                    qos=1,
                )
    except Exception as e:
        logging.error(f"Failed to publish flag capturing started event: {e}")


def handle_flag(client, topic, payload, qos, retain):
    global rasptank_hardware, flag, hit, team, qr, capturing

    try:
        # Handle server msg
        msgs: str = payload.split(" ")
        msg: str = msgs[0]
        if msg == "START_CATCHING":
            capturing = True
            client.publish(STATUS_TOPIC, "Catching flag...", qos=0)
            client.publish(
                topic=GAME_EVENT_TOPIC,
                payload="capturing_flag;captured",
                qos=1,
            )
            rasptank_hardware.led_strip.capturing_animation()
        elif msg == "FLAG_CATCHED":
            flag = True
            capturing = False
            rasptank_hardware.led_strip.flag_possessed()
        elif msg == "FLAG_LOST":
            flag = False
            # Flag not possessed animation ?
        elif msg == "ABORT_CATCHING_SHOT" or msg == "ABORT_CATCHING_EXIT":
            capturing = False
            rasptank_hardware.led_strip.stop_animations()
        elif msg == "ALREADY_GOT" or msg == "NOT_ONBASE":
            client.publish(STATUS_TOPIC, "Cannot catch flag...", qos=0)
        elif msg == "WIN":
            if msgs[1] == "BLUE":
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
        elif msg in ["ENTER_FLAG_AREA", "EXIT_FLAG_AREA"]:
            pass
        else:
            print(f"Unknown message from server's on topic {topic}, msg= {msg}")
            # Behaviour to define depending on msg received : start_catching, already_got, not_onbase, abort_catching_exit
    except Exception as e:
        logger.error(f"Error handling flag command: {e}")


def handle_init(client, topic, payload, qos, retain):
    global team, qr
    try:
        # Handle server msg
        msgs = payload.split(" ")
        if msgs[0] == "TEAM":
            team = msgs[1]
            client.publish(STATUS_TOPIC, f"We are in team {team}", qos=0)
        elif msgs[0] == "QR_CODE":
            qr = msgs[1]
            client.publish(STATUS_TOPIC, f"QR code for scan is : {qr}", qos=0)
        elif msgs[0] == "END":
            client.publish(
                STATUS_TOPIC, f"Initialisation from server successful, let's beat some ass", qos=0
            )
        else:
            print(f"Unknown message from server's on topic {topic}, msg= {msgs}")

    except Exception as e:
        logger.error(f"Error handling init command: {e}")


def handle_shotin(client, topic, payload, qos, retain):
    try:
        # Handle server msg
        msg = payload
        if msg == "SHOT":
            print("TODO freeze the tank")
        else:
            print(f"Unknown message from server's on topic {topic}, msg= {msg}")
    except Exception as e:
        logger.error(f"Error handling shotin command: {e}")


def handle_shotout(client, topic, payload, qos, retain):
    global hit
    try:
        # Handle server msg
        msg = payload
        if msg == "FRIENDLY_FIRE":
            print("TODO stop shooting on friend bro you're stupid")
        elif msg == "SHOT":
            print("TODO headshot")
            hit = hit + 1
        else:
            print(f"Unknown message from server's on topic {topic}, msg= {msg}")
    except Exception as e:
        logger.error(f"Error handling shotin command: {e}")


def handle_qr(client, topic, payload, qos, retain):
    global flag, team, rasptank_hardware
    try:
        msg = payload
        if msg in ["SCAN_SUCCESSFUL", "SCAN_FAILED", "FLAG_DEPOSITED", "NO_FLAG"]:
            client.publish(STATUS_TOPIC, msg, qos=0)
            if msg == "FLAG_DEPOSITED":
                rasptank_hardware.led_strip.scored_animation()
        else:
            print(f"Unknown message from server's on topic {topic}, msg= {msg}")
    except Exception as e:
        logger.error(f"Erreur lors du traitement du scan QR : {e}")


def publish_status_update():
    """Publish periodic status updates."""
    global mqtt_client, running

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

        # Schedule next update if still running
        if running:
            threading.Timer(10.0, publish_status_update).start()

    except Exception as e:
        logger.error(f"Error publishing status update: {e}")


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Rasptank MQTT Control")

    parser.add_argument("--broker", type=str, default="192.168.1.200", help="MQTT broker address")

    parser.add_argument("--port", type=int, default=1883, help="MQTT broker port")

    parser.add_argument("--mock", action="store_true", help="Use mock hardware for testing")

    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    parser.add_argument("--client-id", type=str, default="rasptank", help="MQTT client ID")

    return parser.parse_args()


def main():
    """Main entry point."""
    global mqtt_client, movement_controller, running, tank_id

    # Parse command line arguments
    args = parse_arguments()

    # Set log level based on arguments
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)

    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Initialize MQTT client
        logger.info(f"Initializing MQTT client, connecting to {args.broker}:{args.port}")
        mqtt_client = MQTTClient(
            broker_address=args.broker, broker_port=args.port, client_id=args.client_id
        )

        # Connect to MQTT broker
        mqtt_client.connect()

        # Wait for connection to establish
        if not mqtt_client.wait_for_connection(timeout=10.0):
            logger.error("Failed to connect to MQTT broker")
            return 1
        """
        # Initialize movement controller
        if args.mock:
            # Use mock controller for testing
            logger.info("Initializing mock movement controller")
            movement_controller = MovementFactory.create_movement_controller(
                controller_type=MovementControllerType.MOCK
            )
        else:
            # Use MQTT movement controller
            logger.info("Initializing MQTT movement controller")
            movement_controller = MQTTMovementController(
                mqtt_client=mqtt_client,
                command_topic=MOVEMENT_COMMAND_TOPIC,
                state_topic=MOVEMENT_STATE_TOPIC,
            )
        """
        # Set up handler for shoot commands
        mqtt_client.subscribe(topic=SHOOT_COMMAND_TOPIC, qos=0, callback=handle_shoot_command)

        # Set up handler for camera commands
        mqtt_client.subscribe(topic=CAMERA_COMMAND_TOPIC, qos=0, callback=handle_camera_command)

        # Initialize MQTT Movement Controller
        logger.info("Initializing MQTT Movement Controller")

        movement_controller = MQTTMovementController(
            hardware=rasptank_hardware,
            mqtt_client=mqtt_client,
            command_topic=MOVEMENT_COMMAND_TOPIC,
            state_topic=MOVEMENT_STATE_TOPIC,
        )

        # Initialize Action Controller
        logger.info("Initializing Action Controller")
        action_controller = ActionController(rasptank_hardware)

        # IR Receiver setup
        logger.info("Setting up IR receiver")

        if not rasptank_hardware.ir_receiver.setup_ir_receiver(
            client=mqtt_client, led_command_queue=rasptank_hardware.get_led_command_queue()
        ):
            logger.error("IR receiver setup failed")
            return 1

        time.sleep(0.2)

        # MQTT Subscriptions, tank command topic
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

        # Start periodic status updates
        publish_status_update()

        logger.info("Rasptank initialized and ready for commands")

        # Main loop - keep the program running
        while running:
            time.sleep(0.1)
            # print(team, qr)

            # Call the flag capture logic
            on_flag_area()

            try:
                command = rasptank_hardware.led_command_queue.get(timeout=0.1)
                # Shot received
                if command == "hit":
                    logger.info("Hit event processed in main loop")
                    rasptank_hardware.led_strip.hit_animation()
                    mqtt_client.publish(
                        topic=SHOTIN_TOPIC(tank_id), payload="SHOT_BY " + command, qos=1
                    )
            except Empty:
                pass  # Normal condition, no commands in queue
            except Exception as e:
                logger.error(f"Error in main loop: {e}")

            time.sleep(0.05)  # 50ms

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt detected, exiting...")
    except Exception as e:
        logger.error(f"Error in main loop: {e}")
        return 1
    finally:
        # Clean up resources
        cleanup()

    logger.info("Rasptank shutdown complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
