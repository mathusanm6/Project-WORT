#!/usr/bin/env python3
"""
Main script for Rasptank with MQTT control.
This script initializes all the required components for the Rasptank
to be controlled via MQTT from a PC with a DualSense controller.
"""
import faulthandler

faulthandler.enable()

import argparse
import logging
import signal
import sys
import threading
import time
from queue import Empty

# Import from src.common
from src.common.constants.actions import SHOOT_COMMAND_TOPIC
from src.common.constants.game import STATUS_TOPIC
from src.common.constants.movement import MOVEMENT_COMMAND_TOPIC, MOVEMENT_STATE_TOPIC
from src.common.mqtt.client import MQTTClient
from src.rasptank.action import ActionController
from src.rasptank.movement.controller.mqtt import MQTTMovementController

# Import from src.rasptank
from src.rasptank.rasptank_hardware import RasptankHardware, RasptankLed

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("RasptankMain")

# MQTT Topics
CAMERA_COMMAND_TOPIC = "rasptank/camera/command"

# Global variables for resources that need cleanup
rasptank_hardware = None
rasptank_led = None
mqtt_client = None
movement_controller = None
action_controller = None
running = True


def signal_handler(sig, frame):
    """Handle termination signals gracefully."""
    global running
    logging.info(f"Signal {sig} received. Stopping gracefully...")
    running = False


def cleanup():
    """Clean up all resources."""
    global mqtt_client, movement_controller, action_controller, rasptank_hardware, rasptank_led

    # Clean up movement controller
    if movement_controller:
        try:
            logger.info("Cleaning up movement controller")
            movement_controller.stop()
            movement_controller.cleanup()
        except Exception as e:
            logger.error(f"Error cleaning up movement controller: {e}")

    # Clean up Rasptank hardware (including IR receiver polling)
    if rasptank_hardware:
        try:
            logger.info("Cleaning up Rasptank hardware")
            rasptank_hardware.cleanup()
        except Exception as e:
            logger.error(f"Error cleaning up Rasptank hardware: {e}")

    # Clean up Rasptank LED
    if rasptank_led:
        try:
            logger.info("Cleaning up Rasptank LED")
            rasptank_led.cleanup()
        except Exception as e:
            logger.error(f"Error cleaning up Rasptank LED: {e}")

    # Disconnect MQTT client
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

        # Set LED to indicate shot fired
        try:
            pass
        except Exception as led_error:
            logger.error(f"Error setting LED: {led_error}")

        # Use IRBlast to send the IR signal
        if not action_controller:
            logger.error("Action controller not initialized")
            return

        success = action_controller.shoot(verbose=(logger.level == logging.INFO))

        if success:
            logger.info("IR blast successfully sent")
            # Publish confirmation to allow controller feedback
            client.publish(STATUS_TOPIC, "shot_fired", qos=0)
        else:
            logger.error("Failed to send IR blast")

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

    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    parser.add_argument("--client-id", type=str, default="rasptank", help="MQTT client ID")

    return parser.parse_args()


def main():
    """Main entry point."""
    global rasptank_hardware, rasptank_led, mqtt_client, movement_controller, running

    # Parse command line arguments
    args = parse_arguments()

    # Set log level based on arguments
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)

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

        # Initialize Rasptank hardware
        logger.info("Initializing Rasptank hardware")
        try:
            rasptank_hardware = RasptankHardware()
        except Exception as e:
            logger.error(f"Error initializing Rasptank hardware: {e}")
            return 1

        # Initialize Rasptank LED
        logger.info("Initializing Rasptank LED")
        try:
            rasptank_led = RasptankLed()
        except Exception as e:
            logger.error(f"Error initializing Rasptank LED: {e}")
            return 1

        time.sleep(0.2)  # Give the LED time to initialize

        # Initialize MQTT move  ment controller
        logger.info("Initializing MQTT movement controller")
        movement_controller = MQTTMovementController(
            hardware=rasptank_hardware,
            mqtt_client=mqtt_client,
            command_topic=MOVEMENT_COMMAND_TOPIC,
            state_topic=MOVEMENT_STATE_TOPIC,
        )

        # Initialize action controller
        logger.info("Initializing action controller")
        global action_controller
        action_controller = ActionController(rasptank_hardware)

        # Set up IR receiver for detecting shots
        if rasptank_hardware.setup_ir_receiver(mqtt_client):
            logger.info("IR receiver setup complete")
        else:
            logger.error("IR receiver setup failed")
            return 1

        time.sleep(0.2)  # Give the IR polling thread time to initialize

        # Set up handler for shoot commands
        mqtt_client.subscribe(topic=SHOOT_COMMAND_TOPIC, qos=0, callback=handle_shoot_command)

        # Set up handler for camera commands
        mqtt_client.subscribe(topic=CAMERA_COMMAND_TOPIC, qos=0, callback=handle_camera_command)

        # Start periodic status updates
        publish_status_update()

        logger.info("Rasptank initialized and ready for commands")

        # Main loop - keep the program running
        while running:
            # Set up signal handlers (to avoid MQTT taking over)
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)

            try:
                # Use a small timeout to prevent blocking indefinitely
                command = rasptank_hardware.led_command_queue.get(timeout=0.1)
                if command == "hit":
                    logging.info("Hit event processed in main loop")
                    rasptank_led.hit_animation()
            except Empty:
                # No commands in queue, continue
                pass
            except Exception as e:
                logging.error(f"Error in main loop: {e}")

            # Add a small sleep to reduce CPU usage
            time.sleep(0.1)

    except KeyboardInterrupt:
        logging.info("KeyboardInterrupt detected, exiting gracefully...")
        running = False
    finally:
        logging.info("Cleaning up resources...")
        cleanup()

    logger.info("Rasptank shutdown complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
