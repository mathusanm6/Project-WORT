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
from typing import Dict, List, Optional

from src.common.mqtt.client import MQTTClient
from src.common.mqtt.topics import MOVEMENT_COMMAND_TOPIC, MOVEMENT_STATE_TOPIC
from src.rasptank.movement.controller.mqtt import MQTTMovementController
from src.rasptank.movement.movement_factory import MovementControllerType, MovementFactory

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("RasptankMain")

# MQTT Topics
SHOOT_COMMAND_TOPIC = "rasptank/action/shoot"
CAMERA_COMMAND_TOPIC = "rasptank/camera/command"
STATUS_TOPIC = "rasptank/status"

# Global variables for resources that need cleanup
mqtt_client = None
movement_controller = None
shoot_controller = None
camera_controller = None
running = True


def signal_handler(sig, frame):
    """Handle termination signals gracefully."""
    global running
    logger.info("Termination signal received, shutting down...")
    running = False


def cleanup():
    """Clean up all resources."""
    global mqtt_client, movement_controller, shoot_controller, camera_controller

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

    parser.add_argument("--mock", action="store_true", help="Use mock hardware for testing")

    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    parser.add_argument("--client-id", type=str, default="rasptank", help="MQTT client ID")

    return parser.parse_args()


def main():
    """Main entry point."""
    global mqtt_client, movement_controller, running

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

        # Set up handler for shoot commands
        mqtt_client.subscribe(topic=SHOOT_COMMAND_TOPIC, qos=1, callback=handle_shoot_command)

        # Set up handler for camera commands
        mqtt_client.subscribe(topic=CAMERA_COMMAND_TOPIC, qos=1, callback=handle_camera_command)

        # Start periodic status updates
        publish_status_update()

        logger.info("Rasptank initialized and ready for commands")

        # Main loop - keep the program running
        while running:
            time.sleep(0.1)

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
