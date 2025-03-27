"""Hardware-specific implementation for Rasptank."""

import logging
import threading
import time
import uuid
from enum import Enum
from queue import Queue

import RPi.GPIO as GPIO
from rpi_ws281x import Adafruit_NeoPixel, Color

# Import from src.common
from src.common.constants.game import GAME_EVENT_TOPIC

# Import from src.common
from src.common.enum.movement import (
    CurvedTurnRate,
    SpeedMode,
    ThrustDirection,
    TurnDirection,
    TurnType,
)

# Import from src.rasptank
from src.rasptank.infra_lib import IRBlast, getSignal


class MotorPins(Enum):
    """GPIO pins for motors."""

    MOTOR_A_EN = 4
    MOTOR_B_EN = 17
    MOTOR_A_PIN1 = 14
    MOTOR_A_PIN2 = 15
    MOTOR_B_PIN1 = 27
    MOTOR_B_PIN2 = 18


class IR(Enum):
    """GPIO pins for IR."""

    RECEIVER = 22
    LED_PIN = 23


class RasptankHardware:
    """Hardware-specific implementation for Rasptank."""

    # Direction constants
    DIR_FORWARD = 0
    DIR_BACKWARD = 1

    # Kickstart constants
    KICKSTART_THRESHOLD = 20
    KICKSTART_DUTY_CYCLE = 50
    KICKSTART_DURATION = 0.1

    def __init__(self):
        """Initialize GPIO and motor controllers"""
        self.pwm_A = None
        self.pwm_B = None
        self._setup()
        self.ir_polling_active = True
        self.ir_polling_thread = None
        self.led_command_queue = Queue()

    def _setup(self):
        """Set up GPIO pins and PWM"""
        GPIO.setwarnings(False)
        GPIO.setmode(GPIO.BCM)

        # Set up IR receiver pin
        GPIO.setup(IR.RECEIVER.value, GPIO.IN)

        # Set up motor pins
        GPIO.setup(MotorPins.MOTOR_A_EN.value, GPIO.OUT)
        GPIO.setup(MotorPins.MOTOR_B_EN.value, GPIO.OUT)
        GPIO.setup(MotorPins.MOTOR_A_PIN1.value, GPIO.OUT)
        GPIO.setup(MotorPins.MOTOR_A_PIN2.value, GPIO.OUT)
        GPIO.setup(MotorPins.MOTOR_B_PIN1.value, GPIO.OUT)
        GPIO.setup(MotorPins.MOTOR_B_PIN2.value, GPIO.OUT)

        # Initialize PWM
        try:
            self.pwm_A = GPIO.PWM(MotorPins.MOTOR_A_EN.value, 1000)
            self.pwm_B = GPIO.PWM(MotorPins.MOTOR_B_EN.value, 1000)
            # Start PWM with 0 duty cycle (motors off)
            self.pwm_A.start(0)
            self.pwm_B.start(0)
        except Exception as e:
            print(f"PWM setup error: {e}")

        # Stop motors initially
        self._motor_stop()

    def _motor_stop(self):
        """Stop all motors"""
        GPIO.output(MotorPins.MOTOR_A_PIN1.value, GPIO.LOW)
        GPIO.output(MotorPins.MOTOR_A_PIN2.value, GPIO.LOW)
        GPIO.output(MotorPins.MOTOR_B_PIN1.value, GPIO.LOW)
        GPIO.output(MotorPins.MOTOR_B_PIN2.value, GPIO.LOW)
        # Set duty cycle to 0 to stop motors
        self.pwm_A.ChangeDutyCycle(0)
        self.pwm_B.ChangeDutyCycle(0)

    def _motor_left(self, status, direction, speed_value):
        """Control left motor"""
        if status == 0:  # stop
            GPIO.output(MotorPins.MOTOR_B_PIN1.value, GPIO.LOW)
            GPIO.output(MotorPins.MOTOR_B_PIN2.value, GPIO.LOW)
            self.pwm_B.ChangeDutyCycle(0)
        else:
            if direction == self.DIR_BACKWARD:
                GPIO.output(MotorPins.MOTOR_B_PIN1.value, GPIO.LOW)
                GPIO.output(MotorPins.MOTOR_B_PIN2.value, GPIO.HIGH)
            elif direction == self.DIR_FORWARD:
                GPIO.output(MotorPins.MOTOR_B_PIN1.value, GPIO.HIGH)
                GPIO.output(MotorPins.MOTOR_B_PIN2.value, GPIO.LOW)
            if speed_value < self.KICKSTART_THRESHOLD:
                self.pwm_B.ChangeDutyCycle(self.KICKSTART_DUTY_CYCLE)
                time.sleep(self.KICKSTART_DURATION)
            self.pwm_B.ChangeDutyCycle(int(speed_value))

    def _motor_right(self, status, direction, speed_value):
        """Control right motor"""
        if status == 0:  # stop
            GPIO.output(MotorPins.MOTOR_A_PIN1.value, GPIO.LOW)
            GPIO.output(MotorPins.MOTOR_A_PIN2.value, GPIO.LOW)
            self.pwm_A.ChangeDutyCycle(0)
        else:
            if direction == self.DIR_FORWARD:
                GPIO.output(MotorPins.MOTOR_A_PIN1.value, GPIO.LOW)
                GPIO.output(MotorPins.MOTOR_A_PIN2.value, GPIO.HIGH)
            elif direction == self.DIR_BACKWARD:
                GPIO.output(MotorPins.MOTOR_A_PIN1.value, GPIO.HIGH)
                GPIO.output(MotorPins.MOTOR_A_PIN2.value, GPIO.LOW)
            if speed_value < self.KICKSTART_THRESHOLD:
                self.pwm_A.ChangeDutyCycle(self.KICKSTART_DUTY_CYCLE)
                time.sleep(self.KICKSTART_DURATION)
            self.pwm_A.ChangeDutyCycle(int(speed_value))

    def poll_ir_receiver(self, pin, client, led_queue=None):
        """Continuously poll the IR receiver for signals"""
        logging.info(f"Starting IR receiver polling on pin {pin}...")

        while self.ir_polling_active:
            try:
                # Always ensure GPIO mode is set
                try:
                    GPIO.setmode(GPIO.BCM)
                except Exception:
                    # Mode might already be set, which is fine
                    pass

                shooter = getSignal(pin, True)
                time.sleep(0.01)  # Small delay to prevent CPU overload

                if not shooter:
                    continue

                logging.info(f"Hit detected from shooter: {shooter}")

                # Send a message to the main thread's queue
                if led_queue:
                    led_queue.put("hit")
                    logging.info("LED queue notified about hit")

                # Publish the hit event to the MQTT broker
                if client:
                    message = "hit_by_ir;" + shooter
                    try:
                        client.publish(
                            topic=GAME_EVENT_TOPIC,
                            payload=message,
                            qos=1,
                        )
                    except Exception as e:
                        logging.error(f"Failed to publish hit event: {e}")
                        # Client might be disconnected during shutdown
                        if "disconnected" in str(e).lower():
                            polling_active = False

                # Wait a bit before checking again to avoid multiple triggers
                time.sleep(0.5)

            except Exception as e:
                logging.error(f"Error in IR polling: {e}")
                # If we get persistent GPIO errors, it likely means
                # we're shutting down, so stop polling
                if "GPIO" in str(e) and not polling_active:
                    break
                time.sleep(0.1)

    def setup_ir_receiver(self, client):
        """Set up the IR receiver for detecting hits."""
        try:
            # Start a separate thread for continuous polling
            logging.info("Setting up IR receiver...")
            self.ir_polling_thread = threading.Thread(
                target=self.poll_ir_receiver,
                args=(IR.RECEIVER.value, client, self.led_command_queue),
                daemon=True,
            )
            logging.info(f"Starting IR receiver polling on GPIO {IR.RECEIVER.value}...")
            self.ir_polling_thread.start()
            logging.info("IR receiver setup complete")

            return True
        except Exception as e:
            logging.error(f"Error setting up IR receiver: {e}")
            return False

    def move_hardware(
        self,
        thrust_direction: ThrustDirection,
        turn_direction: TurnDirection,
        turn_type: TurnType,
        speed_mode: SpeedMode,
        curved_turn_rate: CurvedTurnRate,
    ):
        """Direct hardware movement implementation.

        Args:
            thrust_direction (ThrustDirection): FORWARD/BACKWARD/NONE
            turn_direction (TurnDirection): LEFT/RIGHT/NONE
            turn_type (TurnType): SPIN/PIVOT/CURVE/NONE
            speed_mode (SpeedMode): STOP/GEAR_1/GEAR_2/GEAR_3
            curved_turn_rate (CurvedTurnRate): Rate of turn for CURVE turn type (0.0 to 1.0 with 0.0 being no curve)
        """
        speed_value = speed_mode.value
        curved_turn_rate_value = curved_turn_rate.value

        # Forward movement handling
        if thrust_direction == ThrustDirection.FORWARD:
            if turn_direction == TurnDirection.NONE:
                self._motor_left(1, self.DIR_FORWARD, speed_value)
                self._motor_right(1, self.DIR_FORWARD, speed_value)
            elif turn_direction == TurnDirection.LEFT:
                if turn_type == TurnType.CURVE:
                    self._motor_left(
                        1, self.DIR_FORWARD, int(speed_value * (1 - curved_turn_rate_value))
                    )
                    self._motor_right(1, self.DIR_FORWARD, speed_value)
                else:
                    raise ValueError("Turn type must be CURVE for FORWARD + LEFT")
            elif turn_direction == TurnDirection.RIGHT:
                if turn_type == TurnType.CURVE:
                    self._motor_left(1, self.DIR_FORWARD, speed_value)
                    self._motor_right(
                        1, self.DIR_FORWARD, int(speed_value * (1 - curved_turn_rate_value))
                    )
                else:
                    raise ValueError("Turn type must be CURVE for FORWARD + RIGHT")
            else:
                raise ValueError("Invalid turn direction")
            return

        # Backward movement handling
        if thrust_direction == ThrustDirection.BACKWARD:
            if turn_direction == TurnDirection.NONE:
                self._motor_left(1, self.DIR_BACKWARD, speed_value)
                self._motor_right(1, self.DIR_BACKWARD, speed_value)
            elif turn_direction == TurnDirection.LEFT:
                if turn_type == TurnType.CURVE:
                    self._motor_left(
                        1, self.DIR_BACKWARD, int(speed_value * (1 - curved_turn_rate_value))
                    )
                    self._motor_right(1, self.DIR_BACKWARD, speed_value)
                else:
                    raise ValueError("Turn type must be CURVE for BACKWARD + LEFT")
            elif turn_direction == TurnDirection.RIGHT:
                if turn_type == TurnType.CURVE:
                    self._motor_left(1, self.DIR_BACKWARD, speed_value)
                    self._motor_right(
                        1, self.DIR_BACKWARD, int(speed_value * (1 - curved_turn_rate_value))
                    )
                else:
                    raise ValueError("Turn type must be CURVE for BACKWARD + RIGHT")
            else:
                raise ValueError("Invalid turn direction")
            return

        # No thrust (stationary) handling
        if thrust_direction == ThrustDirection.NONE:
            if turn_direction == TurnDirection.NONE:
                self._motor_stop()
            elif turn_direction == TurnDirection.LEFT:
                if turn_type == TurnType.SPIN:
                    self._motor_left(1, self.DIR_BACKWARD, speed_value)
                    self._motor_right(1, self.DIR_FORWARD, speed_value)
                elif turn_type == TurnType.PIVOT:
                    self._motor_left(0, self.DIR_FORWARD, 0)  # stop left motor
                    self._motor_right(1, self.DIR_FORWARD, speed_value)
                elif turn_type == TurnType.CURVE:
                    raise ValueError("CURVE not supported without thrust")
                else:
                    raise ValueError("Turn type should be SPIN or PIVOT for NONE thrust")
            elif turn_direction == TurnDirection.RIGHT:
                if turn_type == TurnType.SPIN:
                    self._motor_left(1, self.DIR_FORWARD, speed_value)
                    self._motor_right(1, self.DIR_BACKWARD, speed_value)
                elif turn_type == TurnType.PIVOT:
                    self._motor_left(1, self.DIR_FORWARD, speed_value)
                    self._motor_right(0, self.DIR_FORWARD, 0)  # stop right motor
                elif turn_type == TurnType.CURVE:
                    raise ValueError("CURVE not supported without thrust")
                else:
                    raise ValueError("Turn type should be SPIN or PIVOT for NONE thrust")
            else:
                raise ValueError("Invalid turn direction")

    def shoot_infrared(self, verbose=False):
        return IRBlast(uuid.getnode(), "LASER", verbose=verbose)

    def cleanup(self):
        """Clean up GPIO and threads."""
        # Stop motors first
        self._motor_stop()

        # Stop PWM safely
        if self.pwm_A:
            self.pwm_A.stop()
        if self.pwm_B:
            self.pwm_B.stop()

        # Stop IR polling thread explicitly
        self.ir_polling_active = False
        if self.ir_polling_thread and self.ir_polling_thread.is_alive():
            self.ir_polling_thread.join(timeout=1.0)
            logging.info("IR polling thread stopped")

        # GPIO cleanup (do this last!)
        GPIO.cleanup()
        logging.info("GPIO cleanup complete")


class LedState(Enum):
    """Enum representing different LED states for game feedback."""

    IDLE = 0
    HIT = 1
    CAPTURING = 2
    FLAG_POSSESSED = 3
    SCORED = 4
    TEAM_BLUE = 5
    TEAM_RED = 6


class RasptankLed:
    """Class for controlling the LED strip on the Rasptank."""

    def __init__(self):
        """Initialize the LED strip."""
        # Set up GPIO
        GPIO.setmode(GPIO.BCM)

        # LED strip configuration
        self.LED_COUNT = 12  # Number of LED pixels
        self.LED_PIN = 12  # GPIO pin connected to the pixels
        self.LED_FREQ_HZ = 800000  # LED signal frequency in hertz
        self.LED_DMA = 10  # DMA channel to use for generating signal
        self.LED_BRIGHTNESS = 255  # 0-255
        self.LED_INVERT = False  # True to invert the signal
        self.LED_CHANNEL = 0  # set to '1' for GPIOs 13, 19, 41, 45 or 53

        # Define colors (R, G, B)
        self.COLOR_RED = (255, 0, 0)
        self.COLOR_BLUE = (0, 0, 255)
        self.COLOR_GREEN = (0, 255, 0)
        self.COLOR_ORANGE = (255, 165, 0)
        self.COLOR_PURPLE = (128, 0, 128)
        self.COLOR_OFF = (0, 0, 0)

        # Thread control
        self.animation_active = False
        self.animation_thread = None
        self.animation_lock = threading.Lock()

        # State tracking
        self.current_state = LedState.IDLE
        self.team_color = self.COLOR_BLUE  # Default team

        # Initialize the strip
        self.strip = Adafruit_NeoPixel(
            self.LED_COUNT,
            self.LED_PIN,
            self.LED_FREQ_HZ,
            self.LED_DMA,
            self.LED_INVERT,
            self.LED_BRIGHTNESS,
            self.LED_CHANNEL,
        )
        self.strip.begin()

        # Turn off all LEDs initially
        self.set_color(self.COLOR_BLUE)

    def set_color(self, color):
        """Set all LEDs to the same color."""
        try:
            # Extract RGB components
            r, g, b = color

            # Set each pixel's color
            for i in range(self.strip.numPixels()):
                self.strip.setPixelColor(i, Color(r, g, b))

            # Update the strip
            self.strip.show()
        except Exception as e:
            logging.error(f"Error setting LED color: {e}")

    def stop_animations(self):
        """Forcefully stop any running animations."""
        self.animation_active = False
        try:
            # Give the thread time to terminate gracefully
            if self.animation_thread and self.animation_thread.is_alive():
                self.animation_thread.join(timeout=0.5)
                self.animation_thread = None
        except Exception as e:
            logging.error(f"Error stopping animation thread: {e}")
        finally:
            if self.animation_lock.locked():
                self.animation_lock.release()
            time.sleep(0.1)  # Short delay ensures hardware readiness

    def set_team(self, team):
        """Set the team color and persist it as the default state."""
        if team.lower() == "blue":
            self.team_color = self.COLOR_BLUE
            self.current_state = LedState.TEAM_BLUE
            self.set_color(self.COLOR_BLUE)
        elif team.lower() == "red":
            self.team_color = self.COLOR_RED
            self.current_state = LedState.TEAM_RED
            self.set_color(self.COLOR_RED)
        else:
            logging.warning(f"Unknown team color: {team}. Using blue as default.")
            self.team_color = self.COLOR_BLUE
            self.current_state = LedState.TEAM_BLUE
            self.set_color(self.COLOR_BLUE)

    def hit_animation(self, duration=2.0):
        """Blink orange when hit."""

        def blink_orange():
            try:
                logging.info("Starting hit animation (orange blinking)")

                self.strip.begin()  # Reinitialize strip in case it was stopped (DO NOT REMOVE: LED won't work without this)

                end_time = time.time() + duration

                while time.time() < end_time and self.animation_active:
                    self.set_color(self.COLOR_ORANGE)
                    time.sleep(0.2)
                    self.set_color(self.COLOR_OFF)
                    time.sleep(0.2)

                if self.animation_active:
                    self.set_color(self.team_color)
                    logging.info("Hit animation complete, returned to team color")
            except Exception as e:
                logging.error(f"Error in hit animation: {e}")
            finally:
                if self.animation_lock.locked():
                    self.animation_lock.release()
                time.sleep(0.1)  # Give hardware time before next action

        # Stop previous animations completely
        self.animation_active = False
        if self.animation_thread and self.animation_thread.is_alive():
            logging.info("Waiting for previous animation to finish")
            self.animation_thread.join(timeout=1.0)

        # Reset stuck lock
        if self.animation_lock.locked():
            logging.info("Lock was stuck; recreating lock")
            self.animation_lock = threading.Lock()

        if self.animation_lock.acquire(blocking=True, timeout=0.5):
            self.animation_active = True
            self.current_state = LedState.HIT
            self.animation_thread = threading.Thread(target=blink_orange, daemon=True)
            self.animation_thread.start()
            logging.info("Hit animation thread started successfully")
            return True
        else:
            logging.error("Failed to acquire lock for hit animation")
            return False

    def capturing_animation(self):
        """Pulse blue to indicate capturing in progress."""

        # Function that will run in a thread
        def pulse_blue():
            try:
                logging.info("Starting capturing animation (blue pulsing)")

                # Pulse until stopped
                while self.animation_active:
                    # Fade up
                    for brightness in range(0, 100, 5):
                        if not self.animation_active:
                            break
                        # Scale blue brightness
                        intensity = int((255 * brightness) / 100)
                        self.set_color((0, 0, intensity))  # Blue with varying brightness
                        time.sleep(0.05)

                    # Fade down
                    for brightness in range(100, 0, -5):
                        if not self.animation_active:
                            break
                        # Scale blue brightness
                        intensity = int((255 * brightness) / 100)
                        self.set_color((0, 0, intensity))  # Blue with varying brightness
                        time.sleep(0.05)

                # Return to team color if animation was externally stopped
                if not self.animation_active:
                    self.set_color(self.team_color)
                    logging.info("Capturing animation stopped, returned to team color")
            except Exception as e:
                logging.error(f"Error in capturing animation: {e}")
            finally:
                # Always release the lock when done
                if self.animation_lock.locked():
                    self.animation_lock.release()

        # Try to acquire the lock and start the animation
        if self.animation_lock.acquire(blocking=False):
            try:
                # Stop any existing animations
                self.stop_animations()

                # Set up the new animation
                self.animation_active = True
                self.current_state = LedState.CAPTURING

                # Start the animation in a new thread
                self.animation_thread = threading.Thread(target=pulse_blue, daemon=True)
                self.animation_thread.start()

                return True
            except Exception as e:
                logging.error(f"Failed to start capturing animation: {e}")
                # Make sure to release the lock if startup fails
                if self.animation_lock.locked():
                    self.animation_lock.release()
                return False
        else:
            logging.warning(
                "Cannot start capturing animation: another animation is already running"
            )
            return False

    def flag_possessed(self):
        """Set all LEDs to purple to indicate flag possession."""
        # Try to acquire the lock
        if self.animation_lock.acquire(blocking=False):
            try:
                # Stop any existing animations
                self.stop_animations()

                # Set state and color
                self.current_state = LedState.FLAG_POSSESSED
                self.set_color(self.COLOR_PURPLE)
                logging.info("Flag possessed state activated (solid purple)")

                # Release the lock since this isn't an animation
                self.animation_lock.release()
                return True
            except Exception as e:
                logging.error(f"Error setting flag possessed state: {e}")
                # Make sure to release the lock if there's an error
                if self.animation_lock.locked():
                    self.animation_lock.release()
                return False
        else:
            logging.warning("Cannot set flag possessed state: an animation is already running")
            return False

    def scored_animation(self, duration=3.0):
        """Flash green to indicate scoring a point.

        Args:
            duration (float): Duration to flash in seconds
        """

        # Function that will run in a thread
        def flash_green():
            try:
                logging.info("Starting scored animation (green flashing)")
                end_time = time.time() + duration

                # Flash until duration ends or animation is stopped
                while time.time() < end_time and self.animation_active:
                    self.set_color(self.COLOR_GREEN)  # Green
                    time.sleep(0.3)
                    self.set_color(self.COLOR_OFF)  # Off
                    time.sleep(0.3)

                # Return to team color if animation wasn't interrupted
                if self.animation_active:
                    self.set_color(self.team_color)
                    logging.info("Scored animation complete, returned to team color")
            except Exception as e:
                logging.error(f"Error in scored animation: {e}")
            finally:
                # Always release the lock when done
                if self.animation_lock.locked():
                    self.animation_lock.release()

        # Try to acquire the lock and start the animation
        if self.animation_lock.acquire(blocking=False):
            try:
                # Stop any existing animations
                self.stop_animations()

                # Set up the new animation
                self.animation_active = True
                self.current_state = LedState.SCORED

                # Start the animation in a new thread
                self.animation_thread = threading.Thread(target=flash_green, daemon=True)
                self.animation_thread.start()

                return True
            except Exception as e:
                logging.error(f"Failed to start scored animation: {e}")
                # Make sure to release the lock if startup fails
                if self.animation_lock.locked():
                    self.animation_lock.release()
                return False
        else:
            logging.warning("Cannot start scored animation: another animation is already running")
            return False

    def reset_to_team_color(self):
        """Reset LEDs to the current team color."""
        # Try to acquire the lock
        if self.animation_lock.acquire(blocking=False):
            try:
                # Stop any existing animations
                self.stop_animations()

                # Set state based on team
                if self.team_color == self.COLOR_BLUE:
                    self.current_state = LedState.TEAM_BLUE
                else:
                    self.current_state = LedState.TEAM_RED

                # Set the color
                self.set_color(self.team_color)
                logging.info(f"Reset to team color")

                # Release the lock since this isn't an animation
                self.animation_lock.release()
                return True
            except Exception as e:
                logging.error(f"Error resetting to team color: {e}")
                # Make sure to release the lock if there's an error
                if self.animation_lock.locked():
                    self.animation_lock.release()
                return False
        else:
            logging.warning("Cannot reset to team color: an animation is already running")
            return False

    def turn_off(self):
        """Turn off all LEDs."""
        # Try to acquire the lock
        if self.animation_lock.acquire(blocking=False):
            try:
                self.strip.begin()  # Reinitialize strip in case it was stopped (DO NOT REMOVE: LED won't work without this)

                # Stop any existing animations
                self.stop_animations()

                # Set state and turn off LEDs
                self.current_state = LedState.IDLE
                self.set_color(self.COLOR_OFF)
                logging.info("LEDs turned off")

                # Release the lock since this isn't an animation
                self.animation_lock.release()
                return True
            except Exception as e:
                logging.error(f"Error turning off LEDs: {e}")
                # Make sure to release the lock if there's an error
                if self.animation_lock.locked():
                    self.animation_lock.release()
                return False
        else:
            logging.warning("Cannot turn off LEDs: an animation is already running")
            return False

    def cleanup(self):
        """Clean up resources before exiting."""
        self.animation_active = False
        if self.animation_thread and self.animation_thread.is_alive():
            self.animation_thread.join(timeout=0.5)

        if self.animation_lock.locked():
            self.animation_lock.release()

        self.turn_off()
        logging.info("LED cleanup complete")
