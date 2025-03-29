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
from queue import Empty

# Import from src.common
from src.common.constants.actions import SHOOT_COMMAND_TOPIC
from src.common.constants.game import FLAG_CAPTURE_DURATION, GAME_EVENT_TOPIC, STATUS_TOPIC
from src.common.constants.movement import MOVEMENT_COMMAND_TOPIC, MOVEMENT_STATE_TOPIC
from src.common.mqtt.client import MQTTClient
from src.rasptank.action import ActionController

# Import from src.rasptank
from src.rasptank.hardware.led_strip import LedStripState
from src.rasptank.hardware.main import RasptankHardware
from src.rasptank.movement.controller.mqtt import MQTTMovementController

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger("RasptankMain")

# MQTT Topics
CAMERA_COMMAND_TOPIC = "rasptank/camera/command"

# Global variables for resources that need cleanup
rasptank_hardware = None
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
    global mqtt_client, movement_controller, action_controller, rasptank_hardware

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

        success = action_controller.shoot(verbose=False)

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


def handle_flag_capture_logic() -> bool:
    """
    Checks whether the Rasptank is on the capture zone and handles
    the full capture logic (timing, MQTT events, animations).
    """
    global rasptank_hardware, mqtt_client

    is_flag_captured = False

    # Track whether the tank is currently on the zone
    is_on_zone = rasptank_hardware.is_on_top_of_capture_zone()

    if not hasattr(handle_flag_capture_logic, "was_on_zone_last_frame"):
        handle_flag_capture_logic.was_on_zone_last_frame = False

    if is_on_zone:
        if not handle_flag_capture_logic.was_on_zone_last_frame:
            # Just entered the zone
            rasptank_hardware.capture_start_time = time.time()
            logging.info("Starting capturing animation")
            rasptank_hardware.led_strip.capturing_animation()

            if mqtt_client:
                try:
                    mqtt_client.publish(
                        topic=GAME_EVENT_TOPIC,
                        payload="capturing_flag;started",
                        qos=1,
                    )
                except Exception as e:
                    logging.error(f"Failed to publish flag capturing started event: {e}")
        else:
            # Still on zone, check duration
            if rasptank_hardware.capture_start_time is not None:
                capture_duration = time.time() - rasptank_hardware.capture_start_time
                if capture_duration >= FLAG_CAPTURE_DURATION:
                    logging.info("Flag captured successfully")
                    rasptank_hardware.led_strip.stop_animations()
                    rasptank_hardware.led_strip.flag_possessed()

                    is_flag_captured = True

                    if mqtt_client:
                        try:
                            mqtt_client.publish(
                                topic=GAME_EVENT_TOPIC,
                                payload="capturing_flag;captured",
                                qos=1,
                            )
                        except Exception as e:
                            logging.error(f"Failed to publish flag captured event: {e}")
                    rasptank_hardware.capture_start_time = None
    else:
        if (
            handle_flag_capture_logic.was_on_zone_last_frame
            and rasptank_hardware.capture_start_time
        ):
            # Just exited the zone before completing capture
            capture_duration = time.time() - rasptank_hardware.capture_start_time
            if capture_duration < FLAG_CAPTURE_DURATION:
                logging.info("Flag capture failed due to insufficient duration")
                rasptank_hardware.led_strip.stop_animations()

                if mqtt_client:
                    try:
                        mqtt_client.publish(
                            topic=GAME_EVENT_TOPIC,
                            payload="capturing_flag;failed",
                            qos=1,
                        )
                    except Exception as e:
                        logging.error(f"Failed to publish flag capture failed event: {e}")
            rasptank_hardware.capture_start_time = None

    # Update tracking for next loop
    handle_flag_capture_logic.was_on_zone_last_frame = is_on_zone

    return is_flag_captured


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
    global rasptank_hardware, mqtt_client, movement_controller, action_controller, running

    # Parse command line arguments
    args = parse_arguments()

    # Configure logging level
    logging_level = logging.DEBUG if args.debug else logging.INFO
    logging.getLogger().setLevel(logging_level)
    logger.setLevel(logging_level)

    # Setup signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Initialize resources
    try:
        # Initialize MQTT Client
        logger.info(f"Connecting to MQTT broker at {args.broker}:{args.port}")
        mqtt_client = MQTTClient(
            broker_address=args.broker, broker_port=args.port, client_id=args.client_id
        )

        if not mqtt_client.connect() or not mqtt_client.wait_for_connection(timeout=10):
            logger.error("Unable to connect to MQTT broker")
            return 1

        # Initialize Rasptank Hardware
        logger.info("Initializing Rasptank hardware")
        rasptank_hardware = RasptankHardware()
        time.sleep(0.2)  # hardware initialization pause

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

        # MQTT Subscriptions
        mqtt_client.subscribe(SHOOT_COMMAND_TOPIC, qos=0, callback=handle_shoot_command)
        mqtt_client.subscribe(CAMERA_COMMAND_TOPIC, qos=0, callback=handle_camera_command)

        # Periodic status updates
        publish_status_update()

        logger.info("Rasptank initialization complete")

        # Main event loop
        while running:
            # Setup signal handlers (once)
            if int(time.time()) % 2 == 0:
                signal.signal(signal.SIGINT, signal_handler)
                signal.signal(signal.SIGTERM, signal_handler)

            # Call the flag capture logic
            handle_flag_capture_logic()

            try:
                command = rasptank_hardware.led_command_queue.get(timeout=0.1)
                if command == "hit":
                    logger.info("Hit event processed in main loop")
                    rasptank_hardware.led_strip.hit_animation()
            except Empty:
                pass  # Normal condition, no commands in queue
            except Exception as e:
                logger.error(f"Error in main loop: {e}")

            time.sleep(0.05)  # 50ms

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt detected, exiting...")
    except Exception as e:
        logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
        return 1
    finally:
        logger.info("Commencing cleanup...")
        cleanup()

    logger.info("Rasptank shutdown complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
