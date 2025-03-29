"""
DualSense Animation System Module
This module provides a non-blocking animation framework for DualSense controller feedback.
"""

import enum
import threading
import time
from typing import Any, Callable, List, Optional, Tuple


class AnimationType(enum.Enum):
    """Types of animations that can be performed."""

    LED = "led"
    RUMBLE = "rumble"
    COMBINED = "combined"


class AnimationPriority(enum.Enum):
    """Priority levels for animations."""

    LOW = 0  # Background effects, can be interrupted by anything
    NORMAL = 1  # Standard effects (most gameplay feedback)
    HIGH = 2  # Important effects (critical gameplay events)
    CRITICAL = 3  # Must-see effects (damage, battery warnings)


class AnimationStep:
    """A single step in an animation sequence."""

    def __init__(
        self,
        duration_ms: int,
        led_color: Optional[Tuple[int, int, int]] = None,
        rumble_values: Optional[Tuple[int, int]] = None,
    ):
        """
        Initialize an animation step.

        Args:
            duration_ms: Duration of this step in milliseconds
            led_color: RGB tuple (0-255) for LED color, or None for no LED change
            rumble_values: Tuple of (low_freq, high_freq) values (0-65535), or None for no rumble
        """
        self.duration_ms = duration_ms
        self.led_color = led_color
        self.rumble_values = rumble_values

    def __repr__(self) -> str:
        return f"AnimationStep(duration_ms={self.duration_ms}, led={self.led_color}, rumble={self.rumble_values})"


class Animation:
    """Defines a sequence of animation steps for the DualSense controller."""

    def __init__(
        self,
        name: str,
        steps: List[AnimationStep],
        priority: AnimationPriority = AnimationPriority.NORMAL,
        loop_count: int = 1,
        restore_led: bool = True,
        restore_led_color: Optional[Tuple[int, int, int]] = None,
        completion_callback: Optional[Callable[[], None]] = None,
    ):
        """
        Initialize an animation.

        Args:
            name: Unique name for the animation
            steps: List of AnimationStep objects defining the animation
            priority: Priority level of this animation
            loop_count: Number of times to loop the animation (0 = infinite)
            restore_led: Whether to restore the LED color after animation completes
            restore_led_color: RGB color to restore to (if None, uses the color before animation)
            completion_callback: Function to call when animation completes normally
        """
        self.name = name
        self.steps = steps
        self.priority = priority
        self.loop_count = loop_count
        self.restore_led = restore_led
        self.restore_led_color = restore_led_color
        self.completion_callback = completion_callback

    def __repr__(self) -> str:
        return f"Animation(name='{self.name}', steps={len(self.steps)}, priority={self.priority})"


class AnimationManager:
    """Manages animations for the DualSense controller."""

    def __init__(self, logger, feedback):
        """
        Initialize the animation manager.

        Args:
            logger: Logger instance for logging animation events
            feedback: DualSenseFeedback instance to control the controller
        """
        self.logger = logger
        self.feedback = feedback

        # Animation state
        self.current_animation = None
        self.animation_thread = None
        self.interrupt_event = threading.Event()
        self.animation_lock = threading.Lock()

        # State tracking
        self.prev_led_color = (255, 255, 255)  # Default white
        self.active_animations = {}  # name -> thread

    def start_animation(self, animation: Animation, force: bool = False) -> bool:
        """
        Start an animation in a background thread.

        Args:
            animation: Animation object to run
            force: If True, interrupt any running animation regardless of priority

        Returns:
            bool: True if animation was started, False otherwise
        """
        with self.animation_lock:
            # Check if we can start this animation
            if self.current_animation:
                if not force and self.current_animation.priority.value >= animation.priority.value:
                    self.logger.debugw(
                        "Animation blocked by higher priority animation",
                        "requested",
                        animation.name,
                        "current",
                        self.current_animation.name,
                        "priority",
                        f"{animation.priority.value} < {self.current_animation.priority.value}",
                    )
                    return False

                # Interrupt the current animation
                self.interrupt_animation(self.current_animation.name)

            # Save the current LED color for restoration if needed
            if animation.restore_led and animation.restore_led_color is None:
                # If we don't have a specific color to restore to, use the current color
                animation.restore_led_color = self.prev_led_color

            # Set as current animation
            self.current_animation = animation
            self.interrupt_event.clear()

            # Start the animation thread
            self.animation_thread = threading.Thread(
                target=self._run_animation, args=(animation,), daemon=True
            )
            self.animation_thread.start()

            # Track the active animation
            self.active_animations[animation.name] = self.animation_thread

            self.logger.debugw(
                "Animation started",
                "name",
                animation.name,
                "priority",
                animation.priority.name,
                "steps",
                len(animation.steps),
            )

            return True

    def interrupt_animation(self, animation_name: str = None) -> bool:
        """
        Interrupt a running animation.

        Args:
            animation_name: Name of animation to interrupt, or None for current

        Returns:
            bool: True if animation was interrupted, False if not found
        """
        with self.animation_lock:
            if animation_name is None and self.current_animation:
                animation_name = self.current_animation.name

            if animation_name in self.active_animations:
                self.logger.debugw("Interrupting animation", "name", animation_name)

                # Set interrupt flag
                self.interrupt_event.set()

                # Wait for thread to exit (with timeout)
                thread = self.active_animations[animation_name]
                thread.join(timeout=0.5)

                # Clean up
                if animation_name in self.active_animations:
                    del self.active_animations[animation_name]

                # Reset interrupt flag for future animations
                self.interrupt_event.clear()

                # Reset current animation if it was the one interrupted
                if self.current_animation and self.current_animation.name == animation_name:
                    self.current_animation = None

                return True

            return False

    def _run_animation(self, animation: Animation) -> None:
        """
        Execute an animation sequence in a background thread.

        Args:
            animation: Animation object to run
        """
        try:
            # Track initial LED color for restoration
            initial_led_color = self.prev_led_color

            # Loop the animation sequence
            loops_completed = 0
            while animation.loop_count == 0 or loops_completed < animation.loop_count:
                # Process each step
                for step in animation.steps:
                    # Check for interruption
                    if self.interrupt_event.is_set():
                        self.logger.debugw(
                            "Animation interrupted",
                            "name",
                            animation.name,
                            "at_step",
                            step,
                            "loops_completed",
                            loops_completed,
                        )
                        return

                    # Apply LED color change if specified
                    if step.led_color is not None:
                        r, g, b = step.led_color
                        self.feedback.set_led_color(r, g, b)
                        self.prev_led_color = step.led_color

                    # Apply rumble if specified
                    if step.rumble_values is not None:
                        low_freq, high_freq = step.rumble_values
                        self.feedback.set_rumble(low_freq, high_freq, step.duration_ms)

                    # Wait for step duration (interruptible)
                    duration_sec = step.duration_ms / 1000.0
                    wait_start = time.time()

                    # Interruptible sleep - check for interrupt every 10ms
                    while time.time() - wait_start < duration_sec:
                        if self.interrupt_event.is_set():
                            self.logger.debugw(
                                "Animation interrupted during wait",
                                "name",
                                animation.name,
                                "at_step",
                                step,
                            )
                            return

                        # Sleep in small increments to remain responsive
                        time.sleep(min(0.01, duration_sec - (time.time() - wait_start)))

                # Increment loop counter
                loops_completed += 1

            # Animation completed normally
            self.logger.debugw(
                "Animation completed", "name", animation.name, "loops", loops_completed
            )

            # Restore LED color if requested
            if animation.restore_led and animation.restore_led_color is not None:
                r, g, b = animation.restore_led_color
                self.feedback.set_led_color(r, g, b)
                self.prev_led_color = animation.restore_led_color

            # Execute completion callback if provided
            if animation.completion_callback:
                try:
                    animation.completion_callback()
                except Exception as e:
                    self.logger.errorw(
                        "Error in animation completion callback",
                        "animation",
                        animation.name,
                        "error",
                        str(e),
                    )

        except Exception as e:
            self.logger.errorw(
                "Error running animation", "animation", animation.name, "error", str(e)
            )
        finally:
            # Clean up regardless of how we exited
            with self.animation_lock:
                if animation.name in self.active_animations:
                    del self.active_animations[animation.name]

                # Reset current animation reference if this was it
                if self.current_animation and self.current_animation.name == animation.name:
                    self.current_animation = None

                # Ensure rumble is stopped
                self.feedback.set_rumble(0, 0, 0)

    def is_animation_running(self, animation_name: str = None) -> bool:
        """
        Check if an animation is currently running.

        Args:
            animation_name: Name of animation to check, or None to check if any animation is running

        Returns:
            bool: True if specified animation is running, or any animation if name=None
        """
        with self.animation_lock:
            if animation_name is None:
                return bool(self.active_animations)
            return animation_name in self.active_animations

    def get_running_animations(self) -> List[str]:
        """
        Get names of all currently running animations.

        Returns:
            List[str]: Names of running animations
        """
        with self.animation_lock:
            return list(self.active_animations.keys())

    def stop_all_animations(self) -> None:
        """Stop all running animations."""
        with self.animation_lock:
            animation_names = list(self.active_animations.keys())

        for name in animation_names:
            self.interrupt_animation(name)

        # Ensure rumble is stopped
        self.feedback.set_rumble(0, 0, 0)

    def cleanup(self) -> None:
        """Clean up resources, stopping all animations."""
        self.stop_all_animations()
