#!/usr/bin/env python3
"""
DualSense Controller Test Utility

This utility helps test and debug DualSense controller mappings.
It displays controller events and outputs button mappings to assist
with configuration of the controller.

This improved version:
1. Creates a small pygame window so keyboard input always works
2. Displays the button mapping and debug mode status in the window
3. Fixes module imports to work with the project structure
"""

import argparse
import logging
import os
import sys
import time
from typing import Dict, List, Optional

import pygame

from src.dashboard.game_controller.dualsense_controller import DualSenseController
from src.dashboard.game_controller.dualsense_mapping import IS_MACOS

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
)
logger = logging.getLogger("ControllerTest")

# Store event history for display
event_history: List[str] = []
MAX_HISTORY = 20  # Maximum number of events to display

# Flags for testing modes
button_mapping_mode = False
debug_all_axis_values = False


def on_button_event(button_name, pressed):
    """Handle button events."""
    status = "pressed" if pressed else "released"
    event_msg = f"Button: {button_name} {status}"
    logger.info(event_msg)
    event_history.append(event_msg)


def on_joystick_event(joystick_name, x_value, y_value):
    """Handle joystick events."""
    if abs(x_value) > 0.1 or abs(y_value) > 0.1:  # Only log significant movements
        event_msg = f"Joystick: {joystick_name} X: {x_value:.2f}, Y: {y_value:.2f}"
        logger.debug(event_msg)
        event_history.append(event_msg)


def on_trigger_event(trigger_name, value):
    """Handle trigger events."""
    if value > 0.1:  # Only log significant trigger presses
        event_msg = f"Trigger: {trigger_name} Value: {value:.2f}"
        logger.debug(event_msg)
        event_history.append(event_msg)


def on_dpad_event(direction, pressed):
    """Handle D-pad events."""
    status = "pressed" if pressed else "released"
    event_msg = f"D-pad: {direction} {status}"
    logger.info(event_msg)
    event_history.append(event_msg)


def test_button_mappings(controller):
    """Run an interactive button mapping test mode."""
    logger.info("=== BUTTON MAPPING TEST MODE ===")
    logger.info("Press each button on the controller to see its ID")
    logger.info("Press Ctrl+C to exit")

    button_states = {}

    start_time = time.time()

    # Run for 60 seconds or until interrupted
    try:
        while time.time() - start_time < 60:
            # Process events
            pygame.event.pump()

            # Check all possible buttons (0-20 range should cover all possibilities)
            for i in range(20):
                if controller.joystick.get_numbuttons() > i:
                    current_state = controller.joystick.get_button(i)

                    # If button state changed from 0 to 1, log it
                    if current_state == 1 and button_states.get(i, 0) == 0:
                        print(f"Button pressed: ID = {i}")
                        logger.info(f"Button pressed: ID = {i}")

                    # Update state
                    button_states[i] = current_state

            # Print axis values if in debug mode
            if debug_all_axis_values:
                axis_values = []
                for i in range(controller.joystick.get_numaxes()):
                    value = controller.joystick.get_axis(i)
                    if abs(value) > 0.1:  # Only show significant values
                        axis_values.append(f"Axis {i}: {value:.2f}")

                if axis_values:
                    print(", ".join(axis_values))

            # Short delay
            time.sleep(0.01)

    except KeyboardInterrupt:
        logger.info("Button mapping test interrupted")

    logger.info("=== BUTTON MAPPING TEST COMPLETE ===")


def display_controller_status(controller):
    """Display the current controller status."""
    status = controller.get_status()

    # Clear screen (platform-dependent)
    if sys.platform.startswith("win"):
        try:
            from os import system

            _ = system("cls")
        except:
            print("\033c", end="")
    else:
        print("\033c", end="")

    # Header
    print("=" * 50)
    print("    DUALSENSE CONTROLLER TEST UTILITY")
    print("=" * 50)

    # Connection status
    print(f"Connected: {'Yes' if status['connected'] else 'No'}")

    # Platform info
    print(f"Platform: {sys.platform} (macOS: {IS_MACOS})")

    # Pressed buttons
    pressed_buttons = [name for name, pressed in status["buttons"].items() if pressed]
    print(f"Pressed buttons: {', '.join(pressed_buttons) if pressed_buttons else 'None'}")

    # Active D-pad directions
    active_dpad = [direction for direction, active in status["dpad"].items() if active]
    print(f"D-pad: {', '.join(active_dpad) if active_dpad else 'None'}")

    # Joystick positions (only if significantly moved)
    left_x, left_y = status["joysticks"]["left"]
    right_x, right_y = status["joysticks"]["right"]

    if abs(left_x) > 0.1 or abs(left_y) > 0.1:
        print(f"Left stick: X={left_x:.2f}, Y={left_y:.2f}")
    else:
        print("Left stick: Centered")

    if abs(right_x) > 0.1 or abs(right_y) > 0.1:
        print(f"Right stick: X={right_x:.2f}, Y={right_y:.2f}")
    else:
        print("Right stick: Centered")

    # Trigger values (only if pressed)
    l2 = status["triggers"]["L2"]
    r2 = status["triggers"]["R2"]

    if l2 > 0.1:
        print(f"L2 trigger: {l2:.2f}")
    else:
        print("L2 trigger: Released")

    if r2 > 0.1:
        print(f"R2 trigger: {r2:.2f}")
    else:
        print("R2 trigger: Released")

    # Event history
    print("\nEvent History:")
    print("-" * 50)
    for event in event_history[-MAX_HISTORY:]:
        print(event)

    # Instructions
    print("\nControls:")
    print("  B - Toggle button mapping mode")
    print("  A - Toggle axis debug mode")
    print("  Q or Ctrl+C - Quit")


def main():
    """Main entry point."""
    global button_mapping_mode, debug_all_axis_values, event_history

    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="DualSense Controller Test Utility",
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument("--debug", "-d", action="store_true", help="Enable debug logging")
    parser.add_argument("--button-test", "-b", action="store_true", help="Run button mapping test")
    parser.add_argument("--axis-debug", "-a", action="store_true", help="Debug all axis values")

    args = parser.parse_args()

    # Set logging level
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)

    # Set test modes from arguments
    button_mapping_mode = args.button_test
    debug_all_axis_values = args.axis_debug

    # Initialize pygame - create a minimal window for key events
    pygame.init()
    pygame.joystick.init()
    screen = pygame.display.set_mode((640, 120))
    pygame.display.set_caption(
        "Controller Test - Press B for button mapping, A for axis debug, Q to quit"
    )
    font = pygame.font.SysFont(None, 24)

    try:
        # Create the controller
        logger.info("Initializing DualSense controller")
        controller = DualSenseController(
            on_button_event=on_button_event,
            on_joystick_event=on_joystick_event,
            on_trigger_event=on_trigger_event,
            on_dpad_event=on_dpad_event,
        )

        # Set up the controller
        if not controller.setup():
            logger.error("Failed to initialize controller")
            return 1

        # If in button mapping test mode, run that and exit
        if button_mapping_mode:
            test_button_mappings(controller)
            controller.cleanup()
            pygame.quit()
            return 0

        # Main loop for interactive testing
        logger.info("Starting interactive controller test")
        event_history.append("Controller initialized")

        update_interval = 0.1  # seconds
        last_update = 0
        running = True

        while running:
            current_time = time.time()

            # On macOS, process events in the main thread
            if IS_MACOS:
                pygame.event.pump()
                controller._process_events()

            # Handle pygame window events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_q:  # Q key
                        running = False
                    elif event.key == pygame.K_b:  # B key
                        button_mapping_mode = not button_mapping_mode
                        msg = f"Button mapping mode: {'On' if button_mapping_mode else 'Off'}"
                        event_history.append(msg)
                        logger.info(msg)
                    elif event.key == pygame.K_a:  # A key
                        debug_all_axis_values = not debug_all_axis_values
                        msg = f"Axis debug mode: {'On' if debug_all_axis_values else 'Off'}"
                        event_history.append(msg)
                        logger.info(msg)

            # Update pygame window
            screen.fill((0, 0, 0))
            text1 = font.render(
                "Controller Test - Press B for button mapping, A for axis debug, Q to quit",
                True,
                (255, 255, 255),
            )
            text2 = font.render(
                f"Button mapping: {'ON' if button_mapping_mode else 'OFF'} | "
                + f"Axis debug: {'ON' if debug_all_axis_values else 'OFF'}",
                True,
                (255, 255, 255),
            )
            screen.blit(text1, (20, 20))
            screen.blit(text2, (20, 60))
            pygame.display.flip()

            # Update display periodically
            if current_time - last_update >= update_interval:
                display_controller_status(controller)
                last_update = current_time

                # In button mapping mode, show raw button IDs
                if button_mapping_mode:
                    for i in range(controller.joystick.get_numbuttons()):
                        if controller.joystick.get_button(i):
                            print(f"Button ID {i} is pressed")

            # Sleep to avoid busy waiting
            time.sleep(0.01)

    except KeyboardInterrupt:
        logger.info("Test interrupted")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        return 1
    finally:
        # Clean up resources
        if "controller" in locals():
            controller.cleanup()
        pygame.quit()

    logger.info("Test complete")
    return 0


if __name__ == "__main__":
    sys.exit(main())
