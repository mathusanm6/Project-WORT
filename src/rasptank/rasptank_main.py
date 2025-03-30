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
from queue import Empty

# Import from src.common
from src.common.constants.actions import SHOOT_COMMAND_TOPIC
from src.common.constants.game import FLAG_CAPTURE_DURATION, GAME_EVENT_TOPIC, STATUS_TOPIC
from src.common.constants.movement import MOVEMENT_COMMAND_TOPIC, MOVEMENT_STATE_TOPIC
from src.common.logging.decorators import log_function_call

# Import from logging system
from src.common.logging.logger_api import Logger, LogLevel
from src.common.logging.logger_factory import LoggerFactory
from src.common.mqtt.client import MQTTClient

# Import from src.rasptank
from src.rasptank.action import ActionController
from src.rasptank.battery_manager import BatteryManager, PowerSource, setup_power_source_prompt
from src.rasptank.hardware.hardware_main import RasptankHardware
from src.rasptank.movement.controller.mqtt import MQTTMovementController

# Global variables for resources that need cleanup
logger: Logger = None
battery_manager: BatteryManager = None
rasptank_hardware: RasptankHardware = None
mqtt_client: MQTTClient = None
movement_controller: MQTTMovementController = None
action_controller: ActionController = None
running = True


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
    global mqtt_client, movement_controller, action_controller, rasptank_hardware, battery_manager, status_update_timer

    # Clean up status update timer
    if "status_update_timer" in globals() and status_update_timer is not None:
        try:
            status_update_timer.cancel()
        except Exception as e:
            logger.errorw("Status update timer cleanup failed", "error", str(e))

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
            logger.infow("Starting flag capture sequence")
            rasptank_hardware.led_strip.capturing_animation()

            if mqtt_client:
                try:
                    mqtt_client.publish(
                        topic=GAME_EVENT_TOPIC,
                        payload="capturing_flag;started",
                        qos=1,
                    )
                except Exception as e:
                    logger.errorw("Failed to publish flag capturing started event", "error", str(e))
        else:
            # Still on zone, check duration
            if rasptank_hardware.capture_start_time is not None:
                capture_duration = time.time() - rasptank_hardware.capture_start_time
                if capture_duration >= FLAG_CAPTURE_DURATION:
                    logger.infow("Flag captured successfully")
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
                            logger.errorw("Failed to publish flag captured event", "error", str(e))
                    rasptank_hardware.capture_start_time = None
    else:
        if (
            handle_flag_capture_logic.was_on_zone_last_frame
            and rasptank_hardware.capture_start_time
        ):
            # Just exited the zone before completing capture
            capture_duration = time.time() - rasptank_hardware.capture_start_time
            if capture_duration < FLAG_CAPTURE_DURATION:
                logger.infow(
                    "Flag capture failed due to insufficient duration",
                    "duration",
                    f"{capture_duration:.2f}s",
                )
                rasptank_hardware.led_strip.stop_animations()

                if mqtt_client:
                    try:
                        mqtt_client.publish(
                            topic=GAME_EVENT_TOPIC,
                            payload="capturing_flag;failed",
                            qos=1,
                        )
                    except Exception as e:
                        logger.errorw(
                            "Failed to publish flag capture failed event", "error", str(e)
                        )
            rasptank_hardware.capture_start_time = None

    # Update tracking for next loop
    handle_flag_capture_logic.was_on_zone_last_frame = is_on_zone

    return is_flag_captured


def publish_status_update():
    """Publish periodic status updates."""
    global mqtt_client, running, logger, battery_manager, status_update_timer

    if not mqtt_client or not running:
        return

    try:
        # Get battery percentage from battery manager
        battery_percent = 100  # Default if no battery manager
        power_source = "wired"

        if battery_manager:
            battery_percent = round(battery_manager.get_battery_percentage())
            power_source = battery_manager.power_source.value

        # Collect status information
        status = {
            "battery": battery_percent,
            "power_source": power_source,
            "timestamp": time.time(),
            # Add other status fields as needed
        }

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
            "timestamp",
            status["timestamp"],
        )

        # Schedule next update if still running - only create a new timer if we're still running
        if running:
            # Store the timer object so we can cancel it if needed
            status_update_timer = threading.Timer(1.0, publish_status_update)
            status_update_timer.daemon = (
                True  # Allow the program to exit even if this thread is running
            )
            status_update_timer.start()

    except Exception as e:
        logger.errorw("Error publishing status update", "error", str(e))
        # Still try to schedule the next update on error
        if running:
            status_update_timer = threading.Timer(1.0, publish_status_update)
            status_update_timer.daemon = True
            status_update_timer.start()


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

    return parser.parse_args()


@log_function_call()
def main():
    """Main entry point."""
    global rasptank_hardware, mqtt_client, movement_controller, action_controller, running, logger, battery_manager
    global status_update_timer
    status_update_timer = None

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

        # Initialize Battery Manager (add after other initializations)
        battery_logger = logger.with_component("battery")
        battery_manager = BatteryManager(battery_logger)

        if args.reset_battery:
            logger.infow("Resetting battery to full charge (100%)")
            battery_manager.reset_battery()

        # Prompt user for power source
        power_source = setup_power_source_prompt(battery_logger)
        battery_manager.set_power_source(power_source)

        # Start battery manager
        battery_manager.start()

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

        # Periodic status updates
        publish_status_update()

        component_logger.infow("Rasptank initialization complete")

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
                    led_logger = logger.with_component("led")
                    led_logger.infow("Hit event processed in main loop")
                    rasptank_hardware.led_strip.hit_animation()
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
