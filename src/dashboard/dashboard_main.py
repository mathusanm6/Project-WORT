#!/usr/bin/env python3
"""
Rasptank Control Dashboard
This is the main entry point for the PC-side control dashboard that
integrates the DualSense controller.
"""

import argparse
import os
import signal
import sys
import time

import pygame

# Import from src.common
from src.common.constants.actions import SCAN_COMMAND_TOPIC, SHOOT_COMMAND_TOPIC, ActionType
from src.common.constants.game import GAME_EVENT_TOPIC, STATUS_TOPIC
from src.common.constants.movement import MOVEMENT_COMMAND_TOPIC
from src.common.enum.movement import (
    CurvedTurnRate,
    SpeedMode,
    ThrustDirection,
    TurnDirection,
    TurnType,
)
from src.common.logging.decorators import log_function_call
from src.common.logging.logger_api import Logger, LogLevel
from src.common.logging.logger_factory import LoggerFactory
from src.common.mqtt.client import MQTTClient

# Import from src.dashboard
from src.dashboard.controller_adapter import ControllerAdapter
from src.dashboard.dualsense.controller import DualSenseController
from src.dashboard.pygame_dashboard import RasptankPygameDashboard

# Global variables
logger: Logger = None
mqtt_client: MQTTClient = None
dualsense_controller: DualSenseController = None
controller_adapter: ControllerAdapter = None
pygame_dashboard: RasptankPygameDashboard = None
running = True
tank_status = {"connected": False, "battery": 0, "power_source": "unknown", "last_update": 0}
current_speed_mode = None


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
        name="RasptankDashboard",
        level=log_level,
        use_colors=True,
    )

    return logger


def signal_handler(sig, frame):
    """Handle termination signals gracefully."""
    global running
    logger.infow("Termination signal received, shutting down...", "signal", sig)
    running = False


@log_function_call()
def send_movement_command(
    thrust_direction: ThrustDirection,
    turn_direction: TurnDirection,
    turn_type: TurnType,
    speed_mode: SpeedMode,
    curved_turn_rate: CurvedTurnRate,
):
    """Send movement commands to the Rasptank via MQTT.

    Args:
        thrust_direction (ThrustDirection): Thrust direction
        turn_direction (TurnDirection): Turn direction
        turn_type (TurnType): Turn type
        speed_mode (SpeedMode): Speed mode
        curved_turn_rate (CurvedTurnRate): Rate of turn for CURVE turn type (0.0 to 1.0 with 0.0 being no curve)
    """
    if not mqtt_client or not mqtt_client.connected.is_set():
        logger.warnw("Cannot send movement command: MQTT client not connected")
        return

    try:
        # Format the movement command
        message = f"{thrust_direction.value};{turn_direction.value};{turn_type.value};{speed_mode.value};{curved_turn_rate.value:.2f}"

        # Publish the command
        logger.debugw(
            "Sending movement command",
            "thrust",
            thrust_direction.value,
            "turn",
            turn_direction.value,
            "type",
            turn_type.value,
            "speed",
            speed_mode.value,
            "curve_rate",
            f"{curved_turn_rate.value:.2f}",
        )

        mqtt_client.publish(MOVEMENT_COMMAND_TOPIC, message, qos=0)

    except Exception as e:
        logger.errorw("Error sending movement command", "error", str(e), exc_info=True)


def send_action_command(action_type: ActionType):
    """Send action commands to the Rasptank via MQTT.

    Args:
        action_type (ActionType): Action
    """
    if not mqtt_client or not mqtt_client.connected.is_set():
        logger.warnw("Cannot send action command", "action", action_type)
        return

    try:
        topic = None
        message = ""

        # Determine the appropriate topic based on the action type
        if action_type == ActionType.SHOOT:
            topic = SHOOT_COMMAND_TOPIC
        elif action_type == ActionType.SCAN:
            topic = SCAN_COMMAND_TOPIC
        else:
            logger.warnw("Unknown action command", "action", action_type)
            return

        # Publish the command
        logger.debugw("Sending action command", "action", action_type, "topic", topic)
        mqtt_client.publish(topic, message, qos=0)

    except Exception as e:
        logger.errorw(
            "Error sending action command", "action", action_type, "error", str(e), exc_info=True
        )


def handle_status_update(client, topic, payload, qos, retain):
    """Handle status updates from the Rasptank.

    Args:
        client (MQTTClient): MQTT client instance
        topic (str): Topic the message was received on
        payload (str): Message payload
        qos (int): QoS level
        retain (bool): Whether the message was retained
    """
    try:
        # Parse the status message
        parts = payload.split(";")

        if len(parts) >= 1:
            status_type = parts[0]

            if status_type == "status" and len(parts) >= 3:
                # Update tank status
                battery = float(parts[1])
                power_source = parts[2]
                timestamp = float(parts[3])

                tank_status["connected"] = True
                tank_status["battery"] = battery
                tank_status["power_source"] = power_source
                tank_status["last_update"] = timestamp

                logger.debugw(
                    "Tank status updated",
                    "battery",
                    battery,
                    "power_source",
                    power_source,
                    "timestamp",
                    timestamp,
                )

            elif status_type == "shot_fired":
                logger.infow("Shot fired by the tank")
            elif status_type == "qr_code_scanning":
                logger.infow("QR code scanning in progress")
            else:
                logger.debugw("Received status update", "payload", payload)

    except Exception as e:
        logger.errorw(
            "Error handling status update", "error", str(e), "payload", payload, exc_info=True
        )


def check_tank_connection_timeout():
    """Check if tank connection has timed out due to no recent status messages."""
    # Define the timeout threshold (30 seconds)
    CONNECTION_TIMEOUT_SECONDS = 6.0

    # Only check if tank was previously marked as connected
    if tank_status["connected"]:
        # Get time since last update
        time_since_update = time.time() - tank_status["last_update"]

        # Check if we've exceeded the timeout
        if time_since_update > CONNECTION_TIMEOUT_SECONDS:
            # Mark tank as disconnected
            tank_status["connected"] = False
            logger.warnw(
                "Tank connection timed out",
                "seconds_since_last_update",
                f"{time_since_update:.1f}",
                "timeout_threshold",
                f"{CONNECTION_TIMEOUT_SECONDS}",
            )


def handle_game_event(client, topic, payload, qos, retain):
    """Handle game events and provide feedback on the controller.

    Args:
        client (MQTTClient): MQTT client instance
        topic (str): Topic the message was received on
        payload (str): Message payload (format: "event_type;[parameters]")
        qos (int): QoS level
        retain (bool): Whether the message was retained
    """
    try:
        parts = payload.split(";")
        if len(parts) < 1:
            return

        event_type = parts[0]
        logger.debugw("Game event received", "event", event_type, "payload", payload)

        # Only process if controller has feedback capabilities
        if (
            not dualsense_controller
            or not hasattr(dualsense_controller, "feedback")
            or not dualsense_controller.has_feedback
        ):
            logger.debugw("Skipping controller feedback - not available")
            return

        # Handle different game events with appropriate feedback
        if event_type == "entering_capture_zone":
            # Entering capture zone - blue pulsing
            logger.debugw("Processing entering capture zone event")
            dualsense_controller.set_led_color(0, 128, 255)  # Light blue
            dualsense_controller.feedback.pulse_rumble(
                intensity=20000, duration_sec=2, pattern_ms=500
            )

        elif event_type == "capturing_flag":
            if len(parts) < 2:
                return

            capture_flag_state = parts[1]
            logger.debugw("Flag capture event", "state", capture_flag_state)

            if capture_flag_state == "started":
                dualsense_controller.feedback_collection.on_capture_flag()
            elif capture_flag_state == "captured":
                dualsense_controller.feedback_collection.on_flag_captured()
            elif capture_flag_state == "failed":
                dualsense_controller.feedback_collection.on_flag_capture_failed()
            else:
                # Unknown state
                logger.warnw("Unknown flag capture state", "state", capture_flag_state)

        elif event_type == "hit_by_ir":
            # Hit by opponent
            shooter = parts[1] if len(parts) > 1 else "Unknown"
            logger.infow("Hit by IR shot", "shooter", shooter)
            dualsense_controller.feedback_collection.on_hit_by_shot()

        elif event_type == "scanning_qr":
            # QR scanning attempt - distinctive feedback
            logger.debugw("Processing QR scanning event")
            dualsense_controller.set_led_color(0, 255, 0)  # Green
            dualsense_controller.set_rumble(10000, 40000, 1000)  # High-frequency feedback

        elif event_type == "flag_returned":
            # Flag returned to base - victory feedback
            logger.debugw("Processing flag returned event")
            dualsense_controller.set_led_color(0, 255, 255)  # Cyan
            dualsense_controller.feedback.pulse_rumble(
                intensity=65535, duration_sec=3, pattern_ms=200
            )

    except Exception as e:
        logger.errorw(
            "Error handling game event", "error", str(e), "payload", payload, exc_info=True
        )


# This function is kept for backwards compatibility but is not used when GUI is available
def print_dashboard():
    """Print a simple text-based dashboard to the console."""
    # Clear the screen (platform-dependent)
    print("\033c", end="")

    # Print header
    print("=" * 50)
    print("   RASPTANK CONTROL DASHBOARD")
    print("=" * 50)

    # Tank status
    print(f"Tank connected: {tank_status['connected']}")
    print(f"Power source:   {tank_status['power_source']}")

    if tank_status["power_source"] == "battery":
        print(f"Battery:       {tank_status['battery']:.2f}%")

    if tank_status["last_update"] > 0:
        time_since_update = time.time() - tank_status["last_update"]
        print(f"Last update:    {time_since_update:.1f} seconds ago")

    # Controller status
    if dualsense_controller:
        controller_status = dualsense_controller.get_status()
        print(
            f"Controller:     {'Connected' if controller_status['connected'] else 'Disconnected'}"
        )
        print(
            f"Feedback:       {'Enabled' if controller_status.get('has_feedback', False) else 'Disabled'}"
        )

        # Movement controller status
        if controller_adapter:
            adapter_status = controller_adapter.get_status()

            global current_speed_mode

            # Display speed mode
            speed_modes = SpeedMode.get_speed_modes()
            formatted_speed_modes = SpeedMode.for_display()
            current_speed_mode_idx = adapter_status.get("current_speed_mode_idx", 0)
            current_speed_mode = adapter_status.get("current_speed_mode", SpeedMode.GEAR_1)
            current_speed_value = adapter_status.get("current_speed_value", SpeedMode.GEAR_1.value)

            current_speed_mode_idx = max(0, min(len(speed_modes) - 1, current_speed_mode_idx))

            print(f"Speed Mode:     {formatted_speed_modes[current_speed_mode_idx]}")

            if adapter_status["last_movement"]:
                (
                    thrust_direction,
                    turn_direction,
                    turn_type,
                    speed_mode,
                    curved_turn_rate,
                ) = adapter_status["last_movement"]
                if (
                    thrust_direction == ThrustDirection.NONE
                    and turn_direction == TurnDirection.NONE
                ):
                    print("Movement:       Stopped")
                else:
                    if turn_type == TurnType.CURVE:
                        print(
                            f"Movement:       {thrust_direction}, {turn_direction}, {turn_type}, {speed_mode} ({current_speed_value}%), {curved_turn_rate} ({curved_turn_rate.value * 100:.0f}%)"
                        )
                    else:
                        print(
                            f"Movement:       {thrust_direction}, {turn_direction}, {turn_type}, {speed_mode} ({current_speed_value}%)"
                        )
            else:
                print("Movement:       Stopped")

            # Show joystick position
            if "joystick_position" in adapter_status:
                x, y = adapter_status["joystick_position"]
                print(f"Joystick:       X: {x:.2f}, Y: {y:.2f}")

        else:
            # Display raw controller info if no movement adapter
            joysticks = controller_status.get("joysticks", {})
            if "left" in joysticks:
                x, y = joysticks["left"]
                if abs(x) > 0.1 or abs(y) > 0.1:
                    print(f"Left Joystick:  X: {x:.2f}, Y: {y:.2f}")

            # Display active buttons
            buttons = controller_status.get("buttons", {})
            active_buttons = [name for name, pressed in buttons.items() if pressed]
            if active_buttons:
                print(f"Active buttons: {', '.join(active_buttons)}")
    else:
        print("Controller:     Disabled")

    if dualsense_controller and dualsense_controller.get_status().get("has_feedback", False):
        print("\n-- FEEDBACK SYSTEM ACTIVE --")

    print("\nPress Ctrl+C to exit")


def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Rasptank MQTT Controller",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    # General arguments
    parser.add_argument(
        "--broker",
        "-b",
        type=str,
        default="192.168.1.200",
        help="MQTT broker address (default: 192.168.1.200)",
    )

    parser.add_argument(
        "--port", "-p", type=int, default=1883, help="MQTT broker port (default: 1883)"
    )

    # Logging options
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level (default: INFO)",
    )

    parser.add_argument("--quiet", "-q", action="store_true", help="Minimize console output")

    # MQTT options
    parser.add_argument(
        "--client-id",
        type=str,
        default=f"rasptank-controller-{time.time_ns() % 10000}",
        help="MQTT client ID (default: auto-generated)",
    )

    # Controller options
    parser.add_argument(
        "--no-controller", action="store_true", help="Don't initialize the DualSense controller"
    )

    parser.add_argument(
        "--no-feedback", action="store_true", help="Disable DualSense LED and rumble feedback"
    )

    parser.add_argument(
        "--test-controller", action="store_true", help="Run controller button mapping test mode"
    )

    # GUI options
    parser.add_argument(
        "--no-gui", action="store_true", help="Disable GUI dashboard and use console only"
    )

    return parser.parse_args()


@log_function_call()
def main():
    """Main entry point."""
    global mqtt_client, dualsense_controller, controller_adapter, running, logger, pygame_dashboard

    # Parse command line arguments
    args = parse_arguments()

    # Set up logging
    log_level = "WARNING" if args.quiet else args.log_level
    logger = create_logger(log_level)

    # Create MQTT logger for the client
    mqtt_logger = logger.with_component("mqtt")

    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    controller_logger = logger.with_component("controller")
    controller_logger.infow("Starting Rasptank Control Dashboard")

    # Add a handler to ensure proper cleanup on exit
    def cleanup_resources():
        """Clean up resources properly before exit."""
        controller_logger.infow("Cleaning up resources")

        # Stop the pygame dashboard
        if pygame_dashboard:
            controller_logger.debugw("Stopping pygame dashboard")
            pygame_dashboard.close()

        if controller_adapter:
            controller_logger.debugw("Stopping movement controller")
            controller_adapter.stop()

        if dualsense_controller:
            controller_logger.debugw("Cleaning up controller")
            # Stop any active rumble effects
            if hasattr(dualsense_controller, "stop_rumble"):
                dualsense_controller.stop_rumble()
            # Reset LED color to white
            if hasattr(dualsense_controller, "set_led_color"):
                dualsense_controller.set_led_color(255, 255, 255)
            # Clean up controller resources
            dualsense_controller.cleanup()

        if mqtt_client:
            controller_logger.debugw("Disconnecting MQTT client")
            mqtt_client.disconnect()

        pygame.quit()
        controller_logger.infow("Resource cleanup complete")

    # Register the cleanup handler
    import atexit

    atexit.register(cleanup_resources)

    dualsense_controller_logger = controller_logger.with_component("dualsense")
    controller_adapter_logger = controller_logger.with_component("controller_adapter")

    try:
        # Initialize pygame early to ensure proper setup on all platforms
        pygame.init()
        pygame.joystick.init()

        # Initialize the pygame dashboard (if not disabled)
        if not args.no_gui:
            controller_logger.infow("Initializing Pygame dashboard")
            pygame_dashboard = RasptankPygameDashboard(
                logger=controller_logger.with_component("pygame_dashboard")
            )
            controller_logger.infow("Pygame dashboard initialized")

        # Initialize DualSense controller first
        if not args.no_controller:
            controller_logger.infow("Initializing DualSense controller")
            # Enable feedback unless explicitly disabled
            enable_feedback = not args.no_feedback

            # Initialize without callbacks - the movement adapter will handle these
            dualsense_controller = DualSenseController(
                dualsense_controller_logger, enable_feedback=enable_feedback
            )

            if not dualsense_controller.setup():
                controller_logger.errorw("Failed to initialize DualSense controller")
                # Continue anyway, we'll retry in the main loop
            else:
                # Log feedback status
                if dualsense_controller.has_feedback:
                    controller_logger.infow("DualSense feedback features (LED & rumble) enabled")
                elif enable_feedback:
                    controller_logger.warnw("DualSense feedback requested but not available")

                # Initialize movement controller with the modified adapter
                controller_logger.infow(
                    "Initializing controller movement adapter with new control scheme"
                )

                controller_adapter = ControllerAdapter(
                    controller_adapter_logger=controller_adapter_logger,
                    controller=dualsense_controller,
                    on_movement_command=send_movement_command,
                    on_action_command=send_action_command,
                )
        else:
            controller_logger.infow("DualSense controller initialization skipped")

        # Initialize MQTT client
        mqtt_logger.infow("Connecting to MQTT broker", "broker", args.broker, "port", args.port)

        mqtt_client = MQTTClient(
            mqtt_logger=mqtt_logger,
            broker_address=args.broker,
            broker_port=args.port,
            client_id=args.client_id,
        )

        # Connect to MQTT broker
        if not mqtt_client.connect():
            controller_logger.errorw("Failed to initiate connection to MQTT broker")
            if dualsense_controller:
                dualsense_controller.cleanup()
            pygame.quit()
            return 1

        # Wait for connection to establish
        if not mqtt_client.wait_for_connection(timeout=5.0):
            controller_logger.errorw("Failed to connect to MQTT broker within timeout")
            if dualsense_controller:
                dualsense_controller.cleanup()
            pygame.quit()
            return 1

        # Subscribe to status updates
        mqtt_client.subscribe(topic=STATUS_TOPIC, qos=0, callback=handle_status_update)

        # Subscribe to game events for controller feedback
        mqtt_client.subscribe(topic=GAME_EVENT_TOPIC, qos=0, callback=handle_game_event)

        controller_logger.infow("Controller initialized and ready")
        controller_logger.infow(
            "Control Scheme:",
            "left_stick",
            "Forward/Backward + turning",
            "l1_r1",
            "Speed control",
            "r2",
            "Shoot",
        )

        # Main loop
        dashboard_update_interval = 1.0 / 24.0  # 24Hz update rate
        last_dashboard_update = 0
        controller_retry_interval = 10.0  # seconds
        last_controller_retry = 0
        connection_check_interval = 1.0  # Check connection status every second
        last_connection_check = 0

        controller_logger.infow("Running with threaded controller polling")

        while running:
            current_time = time.time()

            if dualsense_controller and dualsense_controller.get_status()["connected"]:
                pygame.event.pump()
                dualsense_controller._process_events()

            # Try to connect controller if it's not connected (but not too frequently)
            if (
                dualsense_controller
                and not dualsense_controller.get_status()["connected"]
                and current_time - last_controller_retry >= controller_retry_interval
            ):
                controller_logger.infow("Attempting to reconnect DualSense controller")
                if dualsense_controller.setup(max_retries=1):  # Only try once each time
                    if controller_adapter is None:
                        # Reinitialize movement controller after controller reconnection
                        controller_logger.infow(
                            "Initializing controller movement adapter after reconnection"
                        )
                        controller_adapter = ControllerAdapter(
                            controller_adapter_logger=controller_adapter_logger,
                            controller=dualsense_controller,
                            on_movement_command=send_movement_command,
                            on_action_command=send_action_command,
                        )
                last_controller_retry = current_time

            # Check tank connection status periodically
            if current_time - last_connection_check >= connection_check_interval:
                check_tank_connection_timeout()
                last_connection_check = current_time

            # Update the dashboard periodically
            if current_time - last_dashboard_update >= dashboard_update_interval:
                if pygame_dashboard and pygame_dashboard.running:
                    # Update dashboard data
                    pygame_dashboard.update_tank_status(tank_status)

                    if dualsense_controller:
                        pygame_dashboard.update_controller_status(dualsense_controller.get_status())

                    if controller_adapter:
                        pygame_dashboard.update_movement_status(controller_adapter.get_status())

                    # Update the dashboard display (runs in main thread)
                    pygame_dashboard.update()
                else:
                    if args.no_gui:
                        # Print dashboard to console if GUI is disabled
                        print_dashboard()

                last_dashboard_update = current_time

            # Process any pygame window events - moved to main loop
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

            # Sleep to avoid busy waiting
            time.sleep(0.01)  # 10ms sleep to reduce CPU usage

    except Exception as e:
        controller_logger.errorw("Error in main loop", "error", str(e), exc_info=True)
        return 1
    finally:
        # Most cleanup is handled by the atexit handler
        pass

    controller_logger.infow("Controller shutdown complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
