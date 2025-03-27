#!/usr/bin/env python3
"""
Rasptank Control Dashboard
This is the main entry point for the PC-side control dashboard that
integrates the DualSense controller and prepares for camera integration.

This version uses the new modular controller structure and includes
specific handling for macOS to ensure pygame event handling works correctly.
It also integrates DualSense rumble and LED feedback for enhanced user experience.
"""

import argparse
import logging
import signal
import sys
import time

import pygame

# Import from src.common
from src.common.enum.movement import (
    CurvedTurnRate,
    SpeedMode,
    ThrustDirection,
    TurnDirection,
    TurnType,
)
from src.common.mqtt.client import MQTTClient

# Import from src.dashboard
from src.dashboard.controller_movement_adapter import ControllerMovementAdapter
from src.dashboard.game_controller.dualsense_controller import DualSenseController

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("RasptankMQTT")

# MQTT Topics
MOVEMENT_COMMAND_TOPIC = "rasptank/movement/command"
SHOOT_COMMAND_TOPIC = "rasptank/action/shoot"
CAMERA_COMMAND_TOPIC = "rasptank/camera/command"
ACTION_COMMAND_TOPIC = "rasptank/action/command"
STATUS_TOPIC = "rasptank/status"
GAME_EVENT_TOPIC = "rasptank/game/event"

# Global variables
mqtt_client = None
dualsense_controller = None
movement_controller = None
running = True
tank_status = {"connected": False, "battery": 0, "last_update": 0}


def signal_handler(sig, frame):
    """Handle termination signals gracefully."""
    global running
    logger.info("Termination signal received, shutting down...")
    running = False


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
    global mqtt_client

    if not mqtt_client or not mqtt_client.connected.is_set():
        logger.warning("Cannot send movement command: MQTT client not connected")
        return

    try:
        # Format the movement command
        message = f"{thrust_direction.value};{turn_direction.value};{turn_type.value};{speed_mode.value};{curved_turn_rate.value:.2f}"

        # Publish the command
        logger.debug(f"Sending movement command: {message}")
        mqtt_client.publish(MOVEMENT_COMMAND_TOPIC, message, qos=0)

    except Exception as e:
        logger.error(f"Error sending movement command: {e}")


def send_action_command(action: str):
    """Send action commands to the Rasptank via MQTT.

    Args:
        action (str): Action type (e.g., 'shoot', 'pivot', 'camera')
    """
    global mqtt_client

    if not mqtt_client or not mqtt_client.connected.is_set():
        logger.warning(f"Cannot send {action} command: MQTT client not connected")
        return

    try:
        topic = None
        message = ""

        # Determine the appropriate topic based on the action
        if action == "shoot":
            topic = SHOOT_COMMAND_TOPIC
        elif action == "camera":
            topic = CAMERA_COMMAND_TOPIC
        elif action == "action":
            topic = ACTION_COMMAND_TOPIC
            message = f"{action}"
        else:
            logger.warning(f"Unknown action command: {action}")
            return

        # Publish the command
        logger.debug(f"Sending {action} command: {message}")
        mqtt_client.publish(topic, message, qos=0)

    except Exception as e:
        logger.error(f"Error sending {action} command: {e}")


def handle_status_update(client, topic, payload, qos, retain):
    """Handle status updates from the Rasptank.

    Args:
        client (MQTTClient): MQTT client instance
        topic (str): Topic the message was received on
        payload (str): Message payload
        qos (int): QoS level
        retain (bool): Whether the message was retained
    """
    global tank_status, movement_controller

    try:
        # Parse the status message
        parts = payload.split(";")

        if len(parts) >= 1:
            status_type = parts[0]

            if status_type == "status" and len(parts) >= 3:
                # Update tank status
                battery = int(parts[1])
                timestamp = float(parts[2])

                tank_status["connected"] = True
                tank_status["battery"] = battery
                tank_status["last_update"] = timestamp

                logger.debug(f"Tank status updated: Battery={battery}%")

            elif status_type == "shot_fired":
                logger.info("Shot fired by the tank")
                # Provide shot feedback if controller has feedback
                if dualsense_controller and hasattr(dualsense_controller, "set_rumble"):
                    dualsense_controller.set_rumble(65535, 32768, 300)

            elif status_type == "camera_moved":
                logger.debug("Camera position updated")
            else:
                logger.debug(f"Received status update: {payload}")

    except Exception as e:
        logger.error(f"Error handling status update: {e}")


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

        # Only process if controller has feedback capabilities
        if (
            not dualsense_controller
            or not hasattr(dualsense_controller, "feedback")
            or not dualsense_controller.has_feedback
        ):
            return

        # Handle different game events with appropriate feedback
        if event_type == "entering_capture_zone":
            # Entering capture zone - blue pulsing
            dualsense_controller.set_led_color(0, 128, 255)  # Light blue
            dualsense_controller.feedback.pulse_rumble(
                intensity=20000, duration_sec=2, pattern_ms=500
            )

        elif event_type == "capturing_flag":
            # Flag capture in progress - faster pulsing
            progress = float(parts[1]) if len(parts) > 1 else 0
            intensity = int(20000 + (45535 * progress / 100.0))
            pulse_rate = 500 - int(300 * progress / 100.0)  # Faster pulses as progress increases
            dualsense_controller.feedback.pulse_rumble(
                intensity=intensity, duration_sec=1, pattern_ms=pulse_rate
            )

        elif event_type == "flag_captured":
            # Flag captured - strong victory feedback
            dualsense_controller.set_led_color(0, 0, 255)  # Blue
            dualsense_controller.feedback.pulse_rumble(
                intensity=40000, duration_sec=2, pattern_ms=100
            )

        elif event_type == "hit_by_ir":
            # Hit by opponent - red flash and strong rumble
            dualsense_controller.set_led_color(255, 0, 0)  # Red
            dualsense_controller.set_rumble(65535, 65535, 500)

        elif event_type == "scanning_qr":
            # QR scanning attempt - distinctive feedback
            dualsense_controller.set_led_color(0, 255, 0)  # Green
            dualsense_controller.set_rumble(10000, 40000, 1000)  # High-frequency feedback

        elif event_type == "flag_returned":
            # Flag returned to base - victory feedback
            dualsense_controller.set_led_color(0, 255, 255)  # Cyan
            dualsense_controller.feedback.pulse_rumble(
                intensity=65535, duration_sec=3, pattern_ms=200
            )

    except Exception as e:
        logger.error(f"Error handling game event: {e}")


def print_dashboard():
    """Print a simple text-based dashboard to the console."""
    global tank_status, dualsense_controller, movement_controller

    # Clear the screen (platform-dependent)
    print("\033c", end="")

    # Print header
    print("=" * 50)
    print("   RASPTANK CONTROL DASHBOARD")
    print("=" * 50)

    # Tank status
    print(f"Tank connected: {tank_status['connected']}")
    print(f"Battery level:  {tank_status['battery']}%")

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
        if movement_controller:
            adapter_status = movement_controller.get_status()

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

    print("\n-- CONTROL SCHEME --")
    print("D-Pad:          Movement with spin turning")
    print("Left Stick:     Movement with curve turning")
    print("L1/R1:          Speed control using gears")
    print("R2:             Shoot")
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
    parser.add_argument("--debug", "-d", action="store_true", help="Enable debug logging")

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

    return parser.parse_args()


def setup_logging(debug_mode: bool, quiet_mode: bool):
    """Configure logging based on command line arguments."""
    root_logger = logging.getLogger()

    if debug_mode:
        root_logger.setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)
    elif quiet_mode:
        root_logger.setLevel(logging.WARNING)
        logger.setLevel(logging.WARNING)
    else:
        root_logger.setLevel(logging.INFO)
        logger.setLevel(logging.INFO)


def main():
    """Main entry point."""
    global mqtt_client, dualsense_controller, movement_controller, running

    # Parse command line arguments
    args = parse_arguments()

    # Set up logging
    setup_logging(args.debug, args.quiet)

    # Set up signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Add a handler to ensure proper cleanup on exit
    def cleanup_resources():
        """Clean up resources properly before exit."""
        if movement_controller:
            movement_controller.stop()

        if dualsense_controller:
            # Stop any active rumble effects
            if hasattr(dualsense_controller, "stop_rumble"):
                dualsense_controller.stop_rumble()
            # Reset LED color to white
            if hasattr(dualsense_controller, "set_led_color"):
                dualsense_controller.set_led_color(255, 255, 255)
            # Clean up controller resources
            dualsense_controller.cleanup()

        if mqtt_client:
            mqtt_client.disconnect()

        pygame.quit()

    # Register the cleanup handler
    import atexit

    atexit.register(cleanup_resources)

    try:
        # Initialize pygame early to ensure proper setup on all platforms
        pygame.init()
        pygame.joystick.init()

        # Initialize DualSense controller first
        if not args.no_controller:
            logger.info("Initializing DualSense controller")
            # Enable feedback unless explicitly disabled
            enable_feedback = not args.no_feedback

            # Initialize without callbacks - the movement adapter will handle these
            dualsense_controller = DualSenseController(enable_feedback=enable_feedback)

            if not dualsense_controller.setup():
                logger.error("Failed to initialize DualSense controller")
                # Continue anyway, we'll retry in the main loop
            else:
                # Log feedback status
                if dualsense_controller.has_feedback:
                    logger.info("DualSense feedback features (LED & rumble) enabled")
                elif enable_feedback:
                    logger.warning("DualSense feedback requested but not available")

                # Initialize movement controller with the modified adapter
                logger.info("Initializing controller movement adapter with new control scheme")
                movement_controller = ControllerMovementAdapter(
                    controller=dualsense_controller,
                    on_movement_command=send_movement_command,
                    on_action_command=send_action_command,
                )
        else:
            logger.info("DualSense controller initialization skipped")

        # Initialize MQTT client
        logger.info(f"Connecting to MQTT broker at {args.broker}:{args.port}")
        mqtt_client = MQTTClient(
            broker_address=args.broker, broker_port=args.port, client_id=args.client_id
        )

        # Connect to MQTT broker
        if not mqtt_client.connect():
            logger.error("Failed to initiate connection to MQTT broker")
            if dualsense_controller:
                dualsense_controller.cleanup()
            pygame.quit()
            return 1

        # Wait for connection to establish
        if not mqtt_client.wait_for_connection(timeout=5.0):
            logger.error("Failed to connect to MQTT broker within timeout")
            if dualsense_controller:
                dualsense_controller.cleanup()
            pygame.quit()
            return 1

        # Subscribe to status updates
        mqtt_client.subscribe(topic=STATUS_TOPIC, qos=0, callback=handle_status_update)

        # Subscribe to game events for controller feedback
        mqtt_client.subscribe(topic=GAME_EVENT_TOPIC, qos=0, callback=handle_game_event)

        logger.info("Controller initialized and ready")
        logger.info("Control Scheme:")
        logger.info("- Left Stick: Forward/Backward movement (dead zone: 0.20)")
        logger.info("- Left Stick: Left/Right turning (>0.8 = sharp, 0.2-0.8 = moderate)")
        logger.info("- L1/R1: Speed control (Low, Medium, High)")
        logger.info("- R2: Shoot")

        # Main loop
        dashboard_update_interval = 1.0 / 24.0  # 24Hz update rate
        last_dashboard_update = 0
        controller_retry_interval = 10.0  # seconds
        last_controller_retry = 0

        logger.info("Running with threaded controller polling")

        while running:
            current_time = time.time()

            if dualsense_controller and dualsense_controller.get_status()["connected"]:
                pygame.event.pump()
                dualsense_controller._process_events()

                # Process any pygame window events
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        running = False

            # Try to connect controller if it's not connected (but not too frequently)
            if (
                dualsense_controller
                and not dualsense_controller.get_status()["connected"]
                and current_time - last_controller_retry >= controller_retry_interval
            ):
                logger.info("Attempting to reconnect DualSense controller...")
                if dualsense_controller.setup(max_retries=1):  # Only try once each time
                    if movement_controller is None:
                        # Reinitialize movement controller after controller reconnection
                        logger.info("Initializing controller movement adapter after reconnection")
                        movement_controller = ControllerMovementAdapter(
                            controller=dualsense_controller,
                            on_movement_command=send_movement_command,
                            on_action_command=send_action_command,
                        )
                last_controller_retry = current_time

            # Update the dashboard periodically
            if current_time - last_dashboard_update >= dashboard_update_interval:
                print_dashboard()
                last_dashboard_update = current_time

            # Sleep to avoid busy waiting
            time.sleep(0.005)  # 5ms sleep

    except Exception as e:
        logger.error(f"Error in main loop: {e}", exc_info=True)
        return 1
    finally:
        # Most cleanup is handled by the atexit handler
        pass

    logger.info("Controller shutdown complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
