"""Test Rasptank by performing a series of stunts using the default movement controller.

This script demonstrates the capabilities of the Rasptank by performing a series of stunts.
It directly interacts with the hardware to control the movement of the Rasptank.
"""

import logging
import time

# Import from src.common
from src.common.enum.movement import (
    CurvedTurnRate,
    SpeedMode,
    ThrustDirection,
    TurnDirection,
    TurnType,
)

# Import from src.rasptank
from src.rasptank.hardware.hardware_main import RasptankHardware
from src.rasptank.movement.controller.default import DefaultMovementController


class DefaultMovementControllerTest:
    def __init__(self):
        try:
            # Initialize Rasptank hardware
            self.hardware = RasptankHardware()
        except Exception as e:
            logging.error("Failed to initialize Rasptank hardware")
            raise e

        self.movement_controller = DefaultMovementController(self.hardware)

    def continuous_movement(
        self,
        thrust_direction: ThrustDirection,
        turn_direction: TurnDirection,
        turn_type: TurnType,
        speed_mode: SpeedMode,
        curved_turn_rate: CurvedTurnRate,
        duration: float,
    ):
        """Continuously send movement commands for the specified duration"""
        end_time = time.time() + duration
        while time.time() < end_time:
            self.movement_controller.move(
                thrust_direction, turn_direction, turn_type, speed_mode, curved_turn_rate
            )
            time.sleep(0.1)  # Send command every 0.1 seconds

    def move_forward(self, speed_mode: SpeedMode, duration: float):
        """Move forward for the specified duration"""
        self.continuous_movement(
            ThrustDirection.FORWARD,
            TurnDirection.NONE,
            TurnType.NONE,
            speed_mode,
            CurvedTurnRate.NONE,
            duration,
        )

    def move_backward(self, speed_mode: SpeedMode, duration: float):
        """Move backward for the specified duration"""
        self.continuous_movement(
            ThrustDirection.BACKWARD,
            TurnDirection.NONE,
            TurnType.NONE,
            speed_mode,
            CurvedTurnRate.NONE,
            duration,
        )

    def turn_right_spin(self, speed_mode: SpeedMode, duration: float):
        """Turn right (spin) for the specified duration"""
        self.continuous_movement(
            ThrustDirection.NONE,
            TurnDirection.RIGHT,
            TurnType.SPIN,
            speed_mode,
            CurvedTurnRate.NONE,
            duration,
        )

    def turn_left_spin(self, speed_mode: SpeedMode, duration: float):
        """Turn left (spin) for the specified duration"""
        self.continuous_movement(
            ThrustDirection.NONE,
            TurnDirection.LEFT,
            TurnType.SPIN,
            speed_mode,
            CurvedTurnRate.NONE,
            duration,
        )

    def turn_right_curve(
        self,
        thrust_direction: ThrustDirection,
        speed_mode: SpeedMode,
        curved_turn_rate: CurvedTurnRate,
        duration: float,
    ):
        """Turn right (curve) for the specified duration"""
        self.continuous_movement(
            thrust_direction,
            TurnDirection.RIGHT,
            TurnType.CURVE,
            speed_mode,
            curved_turn_rate,
            duration,
        )

    def turn_left_curve(
        self,
        thrust_direction: ThrustDirection,
        speed_mode: SpeedMode,
        curved_turn_rate: CurvedTurnRate,
        duration: float,
    ):
        """Turn left (curve) for the specified duration"""
        self.continuous_movement(
            thrust_direction,
            TurnDirection.LEFT,
            TurnType.CURVE,
            speed_mode,
            curved_turn_rate,
            duration,
        )

    def turn_right_pivot(self, speed_mode: SpeedMode, duration: float):
        """Turn right (pivot) for the specified duration"""
        self.continuous_movement(
            ThrustDirection.NONE,
            TurnDirection.RIGHT,
            TurnType.PIVOT,
            speed_mode,
            CurvedTurnRate.NONE,
            duration,
        )

    def turn_left_pivot(self, speed_mode: SpeedMode, duration: float):
        """Turn left (pivot) for the specified duration"""
        self.continuous_movement(
            ThrustDirection.NONE,
            TurnDirection.LEFT,
            TurnType.PIVOT,
            speed_mode,
            CurvedTurnRate.NONE,
            duration,
        )

    def stop(self):
        """Stop the Rasptank"""
        self.movement_controller.stop()

    def do_stunt(self, speed_mode: SpeedMode, duration: float, sleep_duration: float):
        """Perform a stunt with the specified speed and duration"""

        print(
            "Performing stunt with Speed: {speed.value}, Duration: {duration}, Sleep duration: {sleep_duration}"
        )
        print("========================================\n")

        print(f"Moving forward for {duration} seconds")
        self.move_forward(SpeedMode.GEAR_3, duration)

        time.sleep(sleep_duration)

        print(f"Moving backward for {duration} seconds")
        self.move_backward(SpeedMode.GEAR_3, duration)

        time.sleep(sleep_duration)

        print(f"Turning right (spin) for {duration} seconds")
        self.turn_right_spin(SpeedMode.GEAR_3, duration)

        time.sleep(sleep_duration)

        print(f"Turning left (spin) for {duration} seconds")
        self.turn_left_spin(SpeedMode.GEAR_3, duration)

        time.sleep(sleep_duration)

        print(f"Going forward and turning right (curve) for {duration} seconds")
        self.turn_right_curve(
            ThrustDirection.FORWARD, SpeedMode.GEAR_3, CurvedTurnRate.HIGH, duration
        )

        time.sleep(sleep_duration)

        print(f"Going backward and turning right (curve) for {duration} seconds")
        self.turn_right_curve(
            ThrustDirection.BACKWARD, SpeedMode.GEAR_3, CurvedTurnRate.HIGH, duration
        )

        time.sleep(sleep_duration)

        print(f"Going forward and turning left (curve) for {duration} seconds")
        self.turn_left_curve(
            ThrustDirection.FORWARD, SpeedMode.GEAR_3, CurvedTurnRate.HIGH, duration
        )

        time.sleep(sleep_duration)

        print(f"Going backward and turning left (curve) for {duration} seconds")
        self.turn_left_curve(
            ThrustDirection.BACKWARD, SpeedMode.GEAR_3, CurvedTurnRate.HIGH, duration
        )

        time.sleep(sleep_duration)

        print(f"Turning right (pivot) for {duration} seconds")
        self.turn_right_pivot(SpeedMode.GEAR_3, duration)

        time.sleep(sleep_duration)

        print(f"Turning left (pivot) for {duration} seconds")
        self.turn_left_pivot(SpeedMode.GEAR_3, duration)

        time.sleep(sleep_duration)

        print("Stopping")
        self.stop()

        time.sleep(sleep_duration)

        print("========================================\n")
        print(
            "\nStunt completed with Speed: {speed.value}, Duration: {duration}, Sleep duration: {sleep_duration}"
        )


if __name__ == "__main__":
    default_movement_controller_test = DefaultMovementControllerTest()

    # Perform the stunt
    print("Performing stunts")
    print("########################################\n")

    # GEAR_3
    default_movement_controller_test.do_stunt(SpeedMode.GEAR_3, 5, 1)

    # GEAR_2
    default_movement_controller_test.do_stunt(SpeedMode.GEAR_2, 5, 1)

    # GEAR_1
    default_movement_controller_test.do_stunt(SpeedMode.GEAR_1, 5, 1)

    print("########################################\n")
    print("All stunts completed")
