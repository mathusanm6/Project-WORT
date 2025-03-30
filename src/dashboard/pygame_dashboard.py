#!/usr/bin/env python3
"""
Enhanced Rasptank Pygame Dashboard
This module provides a graphical dashboard for Rasptank status and controls using pygame,
including a camera feed display area.
"""

import math
import os
import sys
import time

import numpy as np
import pygame

# Import emoji support
try:
    import freetype

    FREETYPE_AVAILABLE = True
except ImportError:
    FREETYPE_AVAILABLE = False

from src.common.camera_client import CameraClient

# Import necessary enums from your existing code
from src.common.enum.movement import (
    CurvedTurnRate,
    SpeedMode,
    ThrustDirection,
    TurnDirection,
    TurnType,
)


class RasptankPygameDashboard:
    """Graphical dashboard for Rasptank controls and status using pygame."""

    def __init__(
        self,
        window_title="Rasptank Control Dashboard",
        camera_server_url="http://100.127.187.15:5000",
    ):
        """Initialize the pygame dashboard.

        Args:
            window_title (str): Title for the dashboard window
            camera_server_url (str): URL of the camera server
        """
        # Make sure pygame is initialized
        if not pygame.get_init():
            pygame.init()

        # Initialize pygame font
        pygame.font.init()

        # Window settings
        self.window_size = (1150, 890)
        self.window = pygame.display.set_mode(self.window_size)
        pygame.display.set_caption(window_title)

        # Set window icon if available
        try:
            # Create a small red tank icon using drawing
            icon_size = 32
            icon = pygame.Surface((icon_size, icon_size), pygame.SRCALPHA)
            # Draw a simplified tank shape
            pygame.draw.rect(icon, (200, 50, 50), (6, 14, 20, 10), border_radius=2)  # Tank body
            pygame.draw.rect(icon, (170, 40, 40), (10, 8, 12, 6))  # Tank turret
            pygame.draw.rect(icon, (180, 45, 45), (14, 4, 4, 8))  # Tank gun
            pygame.draw.rect(icon, (100, 100, 100), (4, 22, 24, 4), border_radius=2)  # Tracks
            pygame.display.set_icon(icon)
        except:
            pass

        # Colors - Modern dark theme with better contrast
        self.colors = {
            "background": (25, 30, 38),  # Darker blue-gray background
            "panel_bg": (32, 37, 45),  # Slightly lighter panel background
            "text": (220, 220, 220),  # Off-white text
            "text_secondary": (150, 155, 160),  # Muted text
            "header": (66, 165, 245),  # Bright blue headers
            "accent": (255, 171, 64),  # Orange accent
            "accent_alt": (255, 193, 94),  # Lighter orange
            "green": (76, 175, 80),  # Material green
            "yellow": (255, 193, 7),  # Material amber
            "red": (244, 67, 54),  # Material red
            "blue": (33, 150, 243),  # Material blue
            "purple": (156, 39, 176),  # Material purple
            "teal": (0, 150, 136),  # Material teal
            "cyan": (0, 188, 212),  # Material cyan
            "border": (55, 60, 68),  # Subtle border color
            "joystick_bg": (40, 45, 53),  # Joystick background
            "grid_line": (55, 60, 68),  # Grid lines
            "overlay_bg": (10, 12, 16, 220),  # Semi-transparent overlay
            "camera_bg": (20, 24, 30),  # Dark background for camera feed
        }

        # Load fonts
        self.load_fonts()

        # Initialize emoji renderer
        self.emoji_renderer = EmojiRenderer()

        # Create emoji map
        self.emojis = {
            "tank": "🔋",  # Battery/Tank icon
            "controller": "🎮",  # Controller icon
            "movement": "🚀",  # Rocket/movement icon
            "controls": "🎛️",  # Control panel icon
            "camera": "📹",  # Camera icon
        }

        # Prerender emojis
        self.emoji_surfaces = {}
        self.prerender_emojis()

        # Flag to control running state
        self.running = True
        self.shutting_down = False
        self.shutdown_start_time = 0

        # State variables
        self.tank_status = {
            "connected": False,
            "battery": 0,
            "power_source": None,
            "last_update": 0,
        }
        self.controller_status = {"connected": False, "has_feedback": False}
        self.movement_status = {
            "current_speed_mode": SpeedMode.GEAR_1,
            "current_speed_mode_idx": 0,
            "current_speed_value": SpeedMode.GEAR_1.value,
            "last_movement": None,
            "joystick_position": (0.0, 0.0),
        }

        # Camera client setup
        self.camera_server_url = camera_server_url
        self.camera_client = None
        self.camera_feed = None
        self.camera_connected = False
        self.last_camera_update = 0
        self.camera_status_message = "Connecting to camera..."
        self.camera_connection_attempts = 0
        self.placeholder_camera_text = "No Camera Feed"

        # Initialize camera client
        try:
            self.camera_client = CameraClient(
                server_url=self.camera_server_url,
                target_fps=30,  # Target 30 frames per second
                num_fetch_threads=2,  # Use 2 parallel fetch threads
                max_queue_size=3,  # Keep a small queue for freshness
                timeout=0.3,  # 300ms timeout for requests
                enable_logging=False,  # Set to True for debugging
            )
            print(
                f"High performance camera client initialized with server URL: {self.camera_server_url}"
            )
            self.start_camera_feed()
        except Exception as e:
            print(f"Error initializing camera client: {e}")
            self.camera_status_message = f"Camera error: {str(e)}"

        # Setting up a separate clock for the dashboard
        self.clock = pygame.time.Clock()

        # UI layout constants
        self.padding = 15
        self.border_radius = 10
        self.section_header_height = 36
        self.layout = self._create_layout()

        # Animation variables
        self.animation_time = 0
        self.pulse_effect = 0

    def load_fonts(self):
        """Load fonts for the dashboard."""
        # Try to use nicer system fonts if available, fallback to default
        try:
            self.fonts = {
                "header": pygame.font.SysFont("Arial", 28, bold=True),
                "title": pygame.font.SysFont("Arial", 20, bold=True),
                "normal": pygame.font.SysFont("Arial", 16),
                "small": pygame.font.SysFont("Arial", 14),
                "icon": pygame.font.SysFont("Arial", 20),
                "large": pygame.font.SysFont("Arial", 36, bold=True),
            }
        except:
            # Fallback to default font
            self.fonts = {
                "header": pygame.font.Font(None, 36),
                "title": pygame.font.Font(None, 28),
                "normal": pygame.font.Font(None, 22),
                "small": pygame.font.Font(None, 18),
                "icon": pygame.font.Font(None, 24),
                "large": pygame.font.Font(None, 42),
            }

    def prerender_emojis(self):
        """Pre-render all emoji characters to surfaces."""
        for key, emoji in self.emojis.items():
            self.emoji_surfaces[key] = self.emoji_renderer.render_emoji(emoji, 24)

    def _create_layout(self):
        """Create the layout for the dashboard with camera feed section."""
        width, height = self.window_size

        # Calculate column widths
        left_col_width = 400  # Left column (status panels)
        right_col_width = width - left_col_width - self.padding * 3  # Camera feed

        # Main sections layout
        layout = {
            # Header section
            "header": pygame.Rect(0, 0, width, 30),
            # Left column - Tank Status
            "tank": pygame.Rect(self.padding, 30 + self.padding, left_col_width, 200),
            # Left column - Controller Status
            "controller": pygame.Rect(
                self.padding, 30 + self.padding * 2 + 200, left_col_width, 190
            ),
            # Left column - Control Scheme
            "controls": pygame.Rect(
                self.padding,
                30 + self.padding * 3 + 190 + 200,
                left_col_width,
                height - (30 + self.padding * 3 + 190 + 200) - self.padding,
            ),
            # Right column - Camera feed (largest section)
            "camera": pygame.Rect(
                self.padding * 3 + left_col_width,
                30 + self.padding,
                right_col_width,
                590 - self.padding,
            ),
            # Right column - Movement status
            "movement": pygame.Rect(
                self.padding * 3 + left_col_width,
                30 + self.padding + 590,
                right_col_width,
                320 - 80,
            ),
        }

        return layout

    def update(self):
        """Update the dashboard window.
        This function should be called from the main thread.
        """
        if not self.running:
            return False

        # Check for window close event
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                if not self.shutting_down:
                    # Start the shutdown sequence
                    self.shutting_down = True
                    self.shutdown_start_time = time.time()
                    # Don't exit immediately, show the message
                return True

        # Update animation timer
        self.animation_time = time.time()
        self.pulse_effect = (math.sin(self.animation_time * 3) + 1) / 2  # Value between 0 and 1

        # Update camera feed
        self.update_camera_feed_from_client()

        # Draw the dashboard
        self.draw_dashboard()

        # If we're shutting down, draw the overlay
        if self.shutting_down:
            self.draw_shutdown_overlay()

            # Check if shutdown time has elapsed
            if time.time() - self.shutdown_start_time > 1.5:
                self.running = False
                return False

        # Update the display
        pygame.display.flip()

        # Cap the frame rate
        self.clock.tick(60)  # 60 FPS

        return True

    def draw_dashboard(self):
        """Draw all dashboard components."""
        # Clear the screen
        self.window.fill(self.colors["background"])

        # Draw main header
        self.draw_main_header()

        # Draw all sections
        self.draw_tank_status_section()
        self.draw_controller_status_section()
        self.draw_movement_status_section()
        self.draw_camera_section()
        self.draw_control_scheme_section()

    def draw_main_header(self):
        """Draw the main header."""
        header_rect = self.layout["header"]

        # Draw gradient background
        self.draw_gradient_rect(
            header_rect,
            (
                self.colors["background"][0],
                self.colors["background"][1],
                self.colors["background"][2],
                255,
            ),
            (
                self.colors["panel_bg"][0],
                self.colors["panel_bg"][1],
                self.colors["panel_bg"][2],
                150,
            ),
        )

        # Draw header text with glow effect
        header_text = self.fonts["header"].render(
            "RASPTANK CONTROL DASHBOARD", True, self.colors["header"]
        )
        glow_value = int(20 + 20 * self.pulse_effect)  # Subtle glow
        glow_color = (
            min(255, self.colors["header"][0] + glow_value),
            min(255, self.colors["header"][1] + glow_value),
            min(255, self.colors["header"][2] + glow_value),
        )

        # Draw glow effect
        glow_text = self.fonts["header"].render("RASPTANK CONTROL DASHBOARD", True, glow_color)
        glow_rect = glow_text.get_rect(
            centerx=header_rect.width // 2, centery=header_rect.height // 2
        )
        self.window.blit(glow_text, glow_rect)

        # Draw main text
        text_rect = header_text.get_rect(
            centerx=header_rect.width // 2, centery=header_rect.height // 2
        )
        self.window.blit(header_text, text_rect)

    def draw_section_header(self, rect, title, icon_key=None):
        """Draw a section header with title and icon.

        Args:
            rect: Rectangle containing the section
            title: Section title
            icon_key: Key to use for the icon from self.emojis
        """
        # Draw header background
        header_rect = pygame.Rect(rect.x, rect.y, rect.width, self.section_header_height)

        # Draw gradient background for header
        self.draw_gradient_rect(
            header_rect,
            (self.colors["header"][0], self.colors["header"][1], self.colors["header"][2], 180),
            (
                self.colors["header"][0] // 2,
                self.colors["header"][1] // 2,
                self.colors["header"][2] // 2,
                150,
            ),
        )

        # Add top rounded corners
        pygame.draw.rect(
            self.window,
            self.colors["header"],
            header_rect,
            width=1,
            border_radius=self.border_radius,
        )

        # Draw icon if provided
        text_x = header_rect.x + 12
        if icon_key and icon_key in self.emoji_surfaces:
            # Use pre-rendered emoji surface
            icon_surface = self.emoji_surfaces[icon_key]
            icon_y = header_rect.y + (self.section_header_height - icon_surface.get_height()) // 2
            self.window.blit(icon_surface, (header_rect.x + 10, icon_y))
            text_x += icon_surface.get_width() + 5

        # Draw section title
        title_text = self.fonts["title"].render(title, True, self.colors["text"])
        self.window.blit(
            title_text,
            (text_x, header_rect.y + (self.section_header_height - title_text.get_height()) // 2),
        )

    def draw_section_body(self, rect):
        """Draw the body background of a section.

        Args:
            rect: Section rectangle
        """
        # Create body rectangle (excluding header)
        body_rect = pygame.Rect(
            rect.x,
            rect.y + self.section_header_height,
            rect.width,
            rect.height - self.section_header_height,
        )

        # Draw semi-transparent panel
        self.draw_rounded_rect(
            body_rect, self.colors["panel_bg"], self.border_radius, bottom_only=True
        )

        # Draw border
        pygame.draw.rect(
            self.window,
            self.colors["border"],
            pygame.Rect(rect.x, rect.y, rect.width, rect.height),
            width=1,
            border_radius=self.border_radius,
        )

    def draw_tank_status_section(self):
        """Draw the tank status section."""
        rect = self.layout["tank"]

        # Draw section header and body
        self.draw_section_header(rect, "Tank Status", "tank")
        self.draw_section_body(rect)

        # Body content
        body_rect = pygame.Rect(
            rect.x,
            rect.y + self.section_header_height,
            rect.width,
            rect.height - self.section_header_height,
        )

        # Connection status
        status_color = self.colors["green"] if self.tank_status["connected"] else self.colors["red"]
        status_text = "Connected" if self.tank_status["connected"] else "Disconnected"

        conn_label = self.fonts["normal"].render("Connection:", True, self.colors["text"])
        conn_value = self.fonts["normal"].render(status_text, True, status_color)

        self.window.blit(conn_label, (body_rect.x + 20, body_rect.y + 20))
        self.window.blit(
            conn_value, (body_rect.x + rect.width - conn_value.get_width() - 20, body_rect.y + 20)
        )

        if self.tank_status["connected"]:
            if self.tank_status["power_source"] == "battery":
                # Battery level with gradient color
                battery_pct = self.tank_status["battery"]
                battery_color = self.get_battery_color(battery_pct)

                batt_label = self.fonts["normal"].render("Battery:", True, self.colors["text"])
                batt_value = self.fonts["normal"].render(f"{battery_pct}%", True, battery_color)

                self.window.blit(batt_label, (body_rect.x + 20, body_rect.y + 55))
                self.window.blit(
                    batt_value,
                    (body_rect.x + rect.width - batt_value.get_width() - 20, body_rect.y + 55),
                )

                # Battery progress bar with gradient
                bar_rect = pygame.Rect(body_rect.x + 20, body_rect.y + 85, body_rect.width - 40, 18)

                # Background
                self.draw_rounded_rect(bar_rect, self.colors["joystick_bg"], 4)

                # Foreground (if battery level > 0)
                if battery_pct > 0:
                    fill_width = int((body_rect.width - 40) * (battery_pct / 100))
                    fill_rect = pygame.Rect(bar_rect.x, bar_rect.y, fill_width, bar_rect.height)

                    # Create gradient from red to green based on battery level
                    if battery_pct <= 20:
                        # Red pulsing when critical
                        alpha = int(200 + 55 * self.pulse_effect) if battery_pct <= 10 else 255
                        self.draw_gradient_rect(
                            fill_rect,
                            (
                                self.colors["red"][0],
                                self.colors["red"][1],
                                self.colors["red"][2],
                                alpha,
                            ),
                            (
                                min(255, self.colors["red"][0] + 30),
                                min(255, self.colors["red"][1] + 30),
                                min(255, self.colors["red"][2] + 30),
                                alpha,
                            ),
                            vertical=False,
                            border_radius=4,
                        )
                    elif battery_pct <= 50:
                        # Yellow to green gradient
                        self.draw_gradient_rect(
                            fill_rect,
                            (
                                self.colors["yellow"][0],
                                self.colors["yellow"][1],
                                self.colors["yellow"][2],
                                255,
                            ),
                            (
                                self.colors["green"][0],
                                self.colors["green"][1],
                                self.colors["green"][2],
                                255,
                            ),
                            vertical=False,
                            border_radius=4,
                        )
                    else:
                        # Green gradient
                        self.draw_gradient_rect(
                            fill_rect,
                            (
                                self.colors["green"][0],
                                self.colors["green"][1],
                                self.colors["green"][2],
                                255,
                            ),
                            (
                                min(255, self.colors["green"][0] + 30),
                                min(255, self.colors["green"][1] + 30),
                                min(255, self.colors["green"][2] + 30),
                                255,
                            ),
                            vertical=False,
                            border_radius=4,
                        )
            else:
                # Power source is not battery
                batt_label = self.fonts["normal"].render("Power Source:", True, self.colors["text"])
                batt_value = self.fonts["normal"].render(
                    self.tank_status["power_source"].capitalize(), True, self.colors["text"]
                )

                self.window.blit(batt_label, (body_rect.x + 20, body_rect.y + 55))
                self.window.blit(
                    batt_value,
                    (body_rect.x + rect.width - batt_value.get_width() - 20, body_rect.y + 55),
                )

            # Last update time with subtle pulsing for recent updates
            last_update = self.tank_status["last_update"]
            if last_update > 0:
                time_since_update = time.time() - last_update
                update_text = f"{time_since_update:.1f} seconds ago"

                # Text gets darker the longer since last update
                alpha = max(120, 255 - min(135, int(time_since_update * 5)))
                text_color = (
                    self.colors["text"][0],
                    self.colors["text"][1],
                    self.colors["text"][2],
                    alpha,
                )

                # Recent updates pulse slightly
                if time_since_update < 5:
                    text_color = (
                        min(255, self.colors["text"][0] + int(20 * self.pulse_effect)),
                        min(255, self.colors["text"][1] + int(20 * self.pulse_effect)),
                        min(255, self.colors["text"][2] + int(20 * self.pulse_effect)),
                    )
            else:
                update_text = "Never"
                text_color = self.colors["text_secondary"]

            update_label = self.fonts["normal"].render("Last Update:", True, self.colors["text"])
            update_value = self.fonts["normal"].render(update_text, True, text_color)

            if self.tank_status["power_source"] == "battery":
                self.window.blit(update_label, (body_rect.x + 20, body_rect.y + 120))
                self.window.blit(
                    update_value,
                    (body_rect.x + rect.width - update_value.get_width() - 20, body_rect.y + 120),
                )
            else:
                self.window.blit(update_label, (body_rect.x + 20, body_rect.y + 90))
                self.window.blit(
                    update_value,
                    (body_rect.x + rect.width - update_value.get_width() - 20, body_rect.y + 90),
                )
        else:
            # If not connected, show a message
            disconnected_text = self.fonts["normal"].render(
                "Tank not connected", True, self.colors["text_secondary"]
            )
            self.window.blit(
                disconnected_text,
                (
                    body_rect.x + (body_rect.width - disconnected_text.get_width()) // 2,
                    body_rect.y + 60,
                ),
            )

    def draw_controller_status_section(self):
        """Draw the controller status section."""
        rect = self.layout["controller"]

        # Draw section header and body
        self.draw_section_header(rect, "Controller Status", "controller")
        self.draw_section_body(rect)

        # Body content
        body_rect = pygame.Rect(
            rect.x,
            rect.y + self.section_header_height,
            rect.width,
            rect.height - self.section_header_height,
        )

        # Connection status
        status_color = (
            self.colors["green"] if self.controller_status["connected"] else self.colors["red"]
        )
        status_text = "Connected" if self.controller_status["connected"] else "Disconnected"

        # Add pulsing effect for connection status
        if self.controller_status["connected"]:
            # Subtle pulse for connected status
            pulse = int(15 * self.pulse_effect)
            status_color = (
                min(255, status_color[0] + pulse),
                min(255, status_color[1] + pulse),
                min(255, status_color[2] + pulse),
            )

        conn_label = self.fonts["normal"].render("Connection:", True, self.colors["text"])
        conn_value = self.fonts["normal"].render(status_text, True, status_color)

        self.window.blit(conn_label, (body_rect.x + 20, body_rect.y + 20))
        self.window.blit(
            conn_value, (body_rect.x + rect.width - conn_value.get_width() - 20, body_rect.y + 20)
        )

        # Feedback status
        feedback_color = (
            self.colors["green"]
            if self.controller_status.get("has_feedback", False)
            else self.colors["text_secondary"]
        )
        feedback_text = (
            "Enabled" if self.controller_status.get("has_feedback", False) else "Disabled"
        )

        feedback_label = self.fonts["normal"].render("Feedback:", True, self.colors["text"])
        feedback_value = self.fonts["normal"].render(feedback_text, True, feedback_color)

        self.window.blit(feedback_label, (body_rect.x + 20, body_rect.y + 55))
        self.window.blit(
            feedback_value,
            (body_rect.x + rect.width - feedback_value.get_width() - 20, body_rect.y + 55),
        )

        # Active buttons (if available)
        buttons = self.controller_status.get("buttons", {})
        active_buttons = [name for name, pressed in buttons.items() if pressed]

        if active_buttons:
            buttons_text = ", ".join(active_buttons)
            if len(buttons_text) > 30:
                buttons_text = buttons_text[:27] + "..."

            buttons_label = self.fonts["normal"].render(
                "Active Buttons:", True, self.colors["text"]
            )
            buttons_value = self.fonts["normal"].render(buttons_text, True, self.colors["cyan"])

            self.window.blit(buttons_label, (body_rect.x + 20, body_rect.y + 90))

            # If text is too long, use smaller font or wrap
            if buttons_value.get_width() > body_rect.width - 160:
                buttons_value = self.fonts["small"].render(buttons_text, True, self.colors["cyan"])

            self.window.blit(buttons_value, (body_rect.x + 160, body_rect.y + 90))

    def draw_movement_status_section(self):
        """Draw the movement status section with smaller joystick."""
        rect = self.layout["movement"]

        # Draw section header and body
        self.draw_section_header(rect, "Movement Status", "movement")
        self.draw_section_body(rect)

        # Body content
        body_rect = pygame.Rect(
            rect.x,
            rect.y + self.section_header_height,
            rect.width,
            rect.height - self.section_header_height,
        )

        # Speed mode with color based on mode
        speed_mode = self.movement_status.get("current_speed_mode", SpeedMode.GEAR_1)
        speed_value = self.movement_status.get("current_speed_value", 25)

        # Choose color based on speed mode
        speed_color = self.colors["green"]  # Default
        if speed_value >= 90:
            speed_color = self.colors["red"]
        elif speed_value >= 70:
            speed_color = self.colors["yellow"]
        elif speed_value >= 50:
            speed_color = self.colors["teal"]

        speed_label = self.fonts["normal"].render("Speed Mode:", True, self.colors["text"])
        speed_value_text = self.fonts["normal"].render(
            f"{speed_mode} ({speed_value}%)", True, speed_color
        )

        self.window.blit(speed_label, (body_rect.x + 15, body_rect.y + 15))
        self.window.blit(speed_value_text, (body_rect.x + 15, body_rect.y + 40))

        # Movement status
        last_movement = self.movement_status.get("last_movement")
        if last_movement:
            (
                thrust_direction,
                turn_direction,
                turn_type,
                speed_mode,
                curved_turn_rate,
            ) = last_movement
            if thrust_direction == ThrustDirection.NONE and turn_direction == TurnDirection.NONE:
                movement_text = "Stopped"
                text_color = self.colors["text_secondary"]
            else:
                # If moving, create descriptive text
                parts = []

                if thrust_direction != ThrustDirection.NONE:
                    parts.append(f"{thrust_direction}")

                if turn_direction != TurnDirection.NONE:
                    turn_text = f"{turn_direction} {turn_type}"
                    if turn_type == TurnType.CURVE and curved_turn_rate != CurvedTurnRate.NONE:
                        turn_text += f" ({curved_turn_rate.value:.1f})"
                    parts.append(turn_text)

                movement_text = ", ".join(parts)

                # Color based on type of movement
                if thrust_direction == ThrustDirection.FORWARD:
                    text_color = self.colors["blue"]
                elif thrust_direction == ThrustDirection.BACKWARD:
                    text_color = self.colors["purple"]
                else:
                    text_color = self.colors["teal"]
        else:
            movement_text = "Stopped"
            text_color = self.colors["text_secondary"]

        movement_label = self.fonts["normal"].render("Movement:", True, self.colors["text"])
        movement_value = self.fonts["normal"].render(movement_text, True, text_color)

        self.window.blit(movement_label, (body_rect.x + 15, body_rect.y + 70))
        self.window.blit(movement_value, (body_rect.x + 15, body_rect.y + 95))

        # Smaller joystick visualization
        joystick_center = (
            body_rect.x + body_rect.width - 100,
            body_rect.y + body_rect.height // 2 - 10,
        )
        joystick_radius = 60  # Smaller radius

        # Draw joystick background with soft shadow
        shadow_radius = joystick_radius + 4
        for i in range(3):  # Soft shadow layers
            shadow_alpha = 70 - i * 20
            pygame.draw.circle(
                self.window,
                (0, 0, 0, shadow_alpha),
                (joystick_center[0] + 2, joystick_center[1] + 2),
                shadow_radius - i,
            )

        # Draw main joystick background
        pygame.draw.circle(
            self.window, self.colors["joystick_bg"], joystick_center, joystick_radius
        )

        # Draw joystick border with subtle glow
        border_color = (
            self.colors["border"][0],
            self.colors["border"][1],
            self.colors["border"][2],
            int(150 + 50 * self.pulse_effect),
        )
        pygame.draw.circle(self.window, border_color, joystick_center, joystick_radius, width=1)

        # Draw grid lines
        pygame.draw.line(
            self.window,
            self.colors["grid_line"],
            (joystick_center[0] - joystick_radius, joystick_center[1]),
            (joystick_center[0] + joystick_radius, joystick_center[1]),
            width=1,
        )
        pygame.draw.line(
            self.window,
            self.colors["grid_line"],
            (joystick_center[0], joystick_center[1] - joystick_radius),
            (joystick_center[0], joystick_center[1] + joystick_radius),
            width=1,
        )

        # Draw subtle grid rings
        for radius in [joystick_radius // 3, joystick_radius * 2 // 3]:
            pygame.draw.circle(
                self.window, self.colors["grid_line"], joystick_center, radius, width=1
            )

        # Draw joystick text labels
        x_label = self.fonts["small"].render("X", True, self.colors["text_secondary"])
        y_label = self.fonts["small"].render("Y", True, self.colors["text_secondary"])

        # Position labels
        self.window.blit(
            x_label, (joystick_center[0] + joystick_radius + 5, joystick_center[1] - 8)
        )
        self.window.blit(
            y_label, (joystick_center[0] - 8, joystick_center[1] - joystick_radius - 16)
        )

        # Draw joystick position text - Above the joystick visualization
        if "joystick_position" in self.movement_status:
            x, y = self.movement_status["joystick_position"]
            joystick_value = self.fonts["small"].render(
                f"X: {x:.2f}, Y: {y:.2f}", True, self.colors["text"]
            )

            # Position the text centered above joystick
            text_x = joystick_center[0] - joystick_value.get_width() // 2
            text_y = joystick_center[1] + joystick_radius + 20

            # Text shadow
            shadow_text = self.fonts["small"].render(
                f"X: {x:.2f}, Y: {y:.2f}", True, (0, 0, 0, 100)
            )
            self.window.blit(shadow_text, (text_x + 1, text_y + 1))

            # Main text
            self.window.blit(joystick_value, (text_x, text_y))

            # Draw joystick position with glow effect
            stick_x = joystick_center[0] + int(x * (joystick_radius - 10))
            stick_y = joystick_center[1] - int(y * (joystick_radius - 10))  # Invert Y axis

            # Draw glow
            glow_radius = 8 + int(2 * self.pulse_effect)
            for i in range(3):
                glow_alpha = 100 - i * 30
                pygame.draw.circle(
                    self.window,
                    (
                        self.colors["red"][0],
                        self.colors["red"][1],
                        self.colors["red"][2],
                        glow_alpha,
                    ),
                    (stick_x, stick_y),
                    glow_radius - i * 2,
                )

            # Draw position marker
            pygame.draw.circle(self.window, self.colors["red"], (stick_x, stick_y), 5)
            pygame.draw.circle(self.window, (255, 255, 255, 150), (stick_x, stick_y), 2)

    def draw_camera_section(self):
        """Draw the camera feed section."""
        rect = self.layout["camera"]

        # Draw section header and body
        self.draw_section_header(rect, "Camera Feed", "camera")
        self.draw_section_body(rect)

        # Body content
        body_rect = pygame.Rect(
            rect.x,
            rect.y + self.section_header_height,
            rect.width,
            rect.height - self.section_header_height,
        )

        # Calculate camera feed display area with padding
        inner_padding = 15
        camera_rect = pygame.Rect(
            body_rect.x + inner_padding,
            body_rect.y + inner_padding,
            body_rect.width - inner_padding * 2,
            body_rect.height - inner_padding * 2,
        )

        # Draw camera feed background
        pygame.draw.rect(self.window, self.colors["camera_bg"], camera_rect)

        # Check camera connection status
        current_time = time.time()
        camera_connected = self.camera_connected and (current_time - self.last_camera_update < 5.0)

        # Draw border with subtle glow based on connection status
        border_color = self.colors["green"] if camera_connected else self.colors["red"]

        # Add pulse effect to border if connected
        if camera_connected:
            border_alpha = int(150 + 50 * self.pulse_effect)
        else:
            border_alpha = 100  # Dimmer when disconnected

        # Create pulsing border
        for i in range(2):
            border_width = 2 - i
            border_alpha_adjusted = max(0, border_alpha - (i * 40))
            pygame.draw.rect(
                self.window,
                (border_color[0], border_color[1], border_color[2], border_alpha_adjusted),
                camera_rect,
                width=border_width,
            )

        # If we have a camera feed, display it
        if self.camera_feed:
            # Scale the feed to fit the display area while maintaining aspect ratio
            feed_width, feed_height = self.camera_feed.get_size()

            # Calculate scaling to fit in the camera_rect while preserving aspect ratio
            scale_x = camera_rect.width / feed_width
            scale_y = camera_rect.height / feed_height
            scale = min(scale_x, scale_y)

            # Scale the feed
            scaled_width = int(feed_width * scale)
            scaled_height = int(feed_height * scale)
            scaled_feed = pygame.transform.smoothscale(
                self.camera_feed, (scaled_width, scaled_height)
            )

            # Center the feed in the camera_rect
            feed_x = camera_rect.x + (camera_rect.width - scaled_width) // 2
            feed_y = camera_rect.y + (camera_rect.height - scaled_height) // 2

            self.window.blit(scaled_feed, (feed_x, feed_y))

            # Show FPS or other camera stats in the corner
            if camera_connected:
                current_time = time.time()

                # Check if we have a new frame since last time
                if self.camera_feed and hasattr(self, "last_frame_id"):
                    # Only update FPS when we actually get a new frame
                    current_frame_id = id(self.camera_feed)  # Use object ID to detect new frames

                    if current_frame_id != self.last_frame_id:
                        # We got a new frame! Update FPS calculation
                        if hasattr(self, "frame_times"):
                            self.frame_times.append(current_time)
                            # Keep only recent frames for FPS calculation (last ~2 seconds)
                            while self.frame_times and current_time - self.frame_times[0] > 2.0:
                                self.frame_times.pop(0)

                            # Calculate actual FPS based on frame count over time period
                            if len(self.frame_times) > 1:
                                time_span = self.frame_times[-1] - self.frame_times[0]
                                if time_span > 0:
                                    actual_fps = (len(self.frame_times) - 1) / time_span
                                    fps_text = self.fonts["small"].render(
                                        f"FPS: {actual_fps:.1f}", True, self.colors["text"]
                                    )
                                    self.window.blit(
                                        fps_text,
                                        (
                                            camera_rect.x + 10,
                                            camera_rect.y
                                            + camera_rect.height
                                            - fps_text.get_height()
                                            - 10,
                                        ),
                                    )
                        else:
                            # Initialize frame tracking
                            self.frame_times = [current_time]

                        # Remember this frame
                        self.last_frame_id = current_frame_id
                else:
                    # Initialize frame tracking
                    self.last_frame_id = id(self.camera_feed) if self.camera_feed else None
                    self.frame_times = [current_time] if self.camera_feed else []
        else:
            # Show placeholder text
            if camera_connected:
                placeholder_text = "Awaiting video stream..."
                text_color = self.colors["text"]
            else:
                placeholder_text = self.camera_status_message
                text_color = self.colors["text_secondary"]

            # Draw placeholder text
            text = self.fonts["normal"].render(placeholder_text, True, text_color)
            text_rect = text.get_rect(center=camera_rect.center)
            self.window.blit(text, text_rect)

            # Draw camera icon for visual appeal
            if not camera_connected:
                # Draw stylized camera icon
                icon_size = 48
                icon_rect = pygame.Rect(
                    camera_rect.centerx - icon_size // 2,
                    camera_rect.centery - icon_size - 20,
                    icon_size,
                    icon_size,
                )
                self.draw_camera_icon(icon_rect)

                # Show connection hint if having trouble connecting
                if self.camera_connection_attempts >= 3:
                    hint_text = self.fonts["small"].render(
                        f"Camera server URL: {self.camera_server_url}", True, self.colors["yellow"]
                    )
                    hint_rect = hint_text.get_rect(
                        centerx=camera_rect.centerx, top=camera_rect.centery + 40
                    )
                    self.window.blit(hint_text, hint_rect)

    def draw_camera_icon(self, rect):
        """Draw a stylized camera icon."""
        # Main camera body
        pygame.draw.rect(self.window, self.colors["text_secondary"], rect, border_radius=5)

        # Lens
        lens_radius = rect.width // 3
        pygame.draw.circle(self.window, self.colors["camera_bg"], rect.center, lens_radius)
        pygame.draw.circle(
            self.window, self.colors["text_secondary"], rect.center, lens_radius, width=2
        )

        # Flash
        flash_rect = pygame.Rect(rect.right - 10, rect.top + 5, 8, 8)
        pygame.draw.rect(self.window, self.colors["yellow"], flash_rect, border_radius=2)

    def draw_control_scheme_section(self):
        """Draw the control scheme section."""
        rect = self.layout["controls"]

        # Draw section header and body
        self.draw_section_header(rect, "Control Scheme", "controls")
        self.draw_section_body(rect)

        # Body content
        body_rect = pygame.Rect(
            rect.x,
            rect.y + self.section_header_height,
            rect.width,
            rect.height - self.section_header_height,
        )

        # Controls with cleaner layout in columns
        control_items_col1 = [
            ("D-Pad", "Moving 4 directions"),
            ("L1 / R1", "Increase / Decrease Speed"),
            ("L2 / R2", "Moving Forward / Backward"),
            ("Left Stick", "Moving with CURVE turn"),
            ("Square", "Shoot Enemy"),
            ("Triangle", "Switch between Spin / Pivot turning"),
        ]

        # Column width
        col_width = body_rect.width // 2 - 30

        # Draw first column
        for i, (control, description) in enumerate(control_items_col1):
            y_pos = body_rect.y + 15 + (i * 30)

            # Control label with slight styling
            control_label = self.fonts["normal"].render(control + ":", True, self.colors["accent"])
            self.window.blit(control_label, (body_rect.x + 20, y_pos))

            # Description with padding
            desc_label = self.fonts["normal"].render(description, True, self.colors["text"])
            self.window.blit(desc_label, (body_rect.x + 120, y_pos))

    def draw_shutdown_overlay(self):
        """Draw the shutdown overlay with message."""
        # Create semi-transparent overlay
        overlay = pygame.Surface(self.window_size, pygame.SRCALPHA)
        overlay.fill(self.colors["overlay_bg"])
        self.window.blit(overlay, (0, 0))

        # Draw the message box
        msg_width, msg_height = 500, 200
        msg_rect = pygame.Rect(
            (self.window_size[0] - msg_width) // 2,
            (self.window_size[1] - msg_height) // 2,
            msg_width,
            msg_height,
        )

        # Draw message box background with glow
        glow_rect = pygame.Rect(
            msg_rect.x - 5, msg_rect.y - 5, msg_rect.width + 10, msg_rect.height + 10
        )

        # Pulsing glow color
        glow_alpha = int(100 + 50 * self.pulse_effect)

        # Draw glowing background
        self.draw_rounded_rect(
            glow_rect,
            (
                self.colors["header"][0],
                self.colors["header"][1],
                self.colors["header"][2],
                glow_alpha,
            ),
            15,
        )

        # Draw message box
        self.draw_rounded_rect(msg_rect, self.colors["panel_bg"], 10)
        pygame.draw.rect(self.window, self.colors["border"], msg_rect, width=2, border_radius=10)

        # Draw message
        title_text = self.fonts["large"].render("Shutting Down", True, self.colors["red"])
        title_rect = title_text.get_rect(centerx=msg_rect.centerx, top=msg_rect.top + 30)
        self.window.blit(title_text, title_rect)

        # Draw message with animation dots
        dots = "." * (int(time.time() * 3) % 4)  # Animated dots
        message_text = self.fonts["normal"].render(f"Please wait{dots}", True, self.colors["text"])
        message_rect = message_text.get_rect(centerx=msg_rect.centerx, top=title_rect.bottom + 30)
        self.window.blit(message_text, message_rect)

        # Draw spinner animation
        spinner_center = (msg_rect.centerx, message_rect.bottom + 40)
        self.draw_spinner(spinner_center, 20, 6)

    def draw_spinner(self, center, radius, width):
        """Draw a loading spinner animation."""
        angle = (time.time() * 360) % 360  # Rotation angle

        # Draw spinner segments with gradual fade
        for i in range(0, 360, 30):
            alpha = int(255 * (1 - ((i - angle) % 360) / 360))
            color = (
                self.colors["accent"][0],
                self.colors["accent"][1],
                self.colors["accent"][2],
                alpha,
            )

            start_angle = math.radians(i)
            end_angle = math.radians(i + 15)

            # Draw an arc
            pygame.draw.arc(
                self.window,
                color,
                (center[0] - radius, center[1] - radius, radius * 2, radius * 2),
                start_angle,
                end_angle,
                width,
            )

    def get_battery_color(self, level):
        """Get appropriate color for battery level."""
        if level <= 20:
            return self.colors["red"]
        elif level <= 50:
            return self.colors["yellow"]
        else:
            return self.colors["green"]

    def draw_rounded_rect(self, rect, color, radius=10, width=0, bottom_only=False):
        """Draw a rounded rectangle.

        Args:
            rect: Rectangle to draw
            color: Color to use
            radius: Corner radius
            width: Border width (0 for filled)
            bottom_only: If True, only round bottom corners
        """
        if bottom_only:
            # Draw a rectangle with only bottom corners rounded
            pygame.draw.rect(
                self.window,
                color,
                rect,
                width=width,
                border_bottom_left_radius=radius,
                border_bottom_right_radius=radius,
            )
        else:
            pygame.draw.rect(self.window, color, rect, width=width, border_radius=radius)

    def draw_gradient_rect(self, rect, color_start, color_end, vertical=True, border_radius=0):
        """Draw a rectangle with a gradient fill.

        Args:
            rect: Rectangle to draw
            color_start: Starting color (r,g,b,a)
            color_end: Ending color (r,g,b,a)
            vertical: If True, gradient goes top to bottom, else left to right
            border_radius: Corner radius
        """
        # Create a surface with per-pixel alpha
        surface = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)

        # Draw the gradient
        if vertical:
            for y in range(rect.height):
                # Calculate color for this line
                alpha = y / (rect.height - 1) if rect.height > 1 else 0
                color = (
                    int(color_start[0] * (1 - alpha) + color_end[0] * alpha),
                    int(color_start[1] * (1 - alpha) + color_end[1] * alpha),
                    int(color_start[2] * (1 - alpha) + color_end[2] * alpha),
                    int(color_start[3] * (1 - alpha) + color_end[3] * alpha),
                )
                pygame.draw.line(surface, color, (0, y), (rect.width, y))
        else:
            for x in range(rect.width):
                # Calculate color for this line
                alpha = x / (rect.width - 1) if rect.width > 1 else 0
                color = (
                    int(color_start[0] * (1 - alpha) + color_end[0] * alpha),
                    int(color_start[1] * (1 - alpha) + color_end[1] * alpha),
                    int(color_start[2] * (1 - alpha) + color_end[2] * alpha),
                    int(color_start[3] * (1 - alpha) + color_end[3] * alpha),
                )
                pygame.draw.line(surface, color, (x, 0), (x, rect.height))

        # Apply border radius if needed
        if border_radius > 0:
            # Create a mask surface
            mask = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
            # Draw a rect with the desired border radius
            pygame.draw.rect(
                mask, (255, 255, 255), (0, 0, rect.width, rect.height), border_radius=border_radius
            )
            # Apply the mask to the gradient surface
            surface.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MIN)

        # Blit the gradient surface to the window
        self.window.blit(surface, rect)

    def update_tank_status(self, status):
        """Update the tank status display.

        Args:
            status (dict): Tank status information
        """
        self.tank_status.update(status)

    def update_controller_status(self, status):
        """Update the controller status display.

        Args:
            status (dict): Controller status information
        """
        self.controller_status.update(status)

    def update_movement_status(self, status):
        """Update the movement status display.

        Args:
            status (dict): Movement status information
        """
        self.movement_status.update(status)

    def start_camera_feed(self):
        """Initialize and start the camera feed."""
        if not self.camera_client:
            print("Camera client not initialized")
            return

        try:
            print("Starting camera feed")
            # Start continuous frame fetching
            self.camera_client.start_continuous_frames()
            self.camera_status_message = "Connecting to camera..."
            print("Camera feed started")
        except Exception as e:
            print(f"Error starting camera feed: {e}")
            self.camera_status_message = f"Camera error: {str(e)}"
            self.camera_connected = False

    def update_camera_feed_from_client(self):
        """Fetch the latest frame from the camera client and update the display."""
        if not self.camera_client:
            return

        try:
            # Get frame as pygame surface with short age requirement for max freshness
            surface = self.camera_client.get_frame_as_pygame_surface(max_age_seconds=0.05)

            if surface:
                self.camera_feed = surface
                self.camera_connected = True

                # Track frame rates and update times
                current_time = time.time()
                time_since_update = current_time - self.last_camera_update
                self.last_camera_update = current_time

                # Restart camera feed if it seems stalled
                if time_since_update > 3.0:
                    print("Camera feed seems stalled, restarting...")
                    self.stop_camera_feed()
                    self.start_camera_feed()

            elif time.time() - self.last_camera_update > 5.0:
                # If no frames for a while, increment connection attempts
                self.camera_connection_attempts += 1
                self.camera_status_message = "Waiting for camera feed..."

                # After several attempts, try restarting the feed
                if self.camera_connection_attempts % 3 == 0:
                    print("No frames received, restarting camera feed...")
                    self.stop_camera_feed()
                    time.sleep(0.5)  # Short delay before reconnecting
                    self.start_camera_feed()

        except Exception as e:
            print(f"Error updating camera feed: {e}")
            if self.camera_connected:
                self.camera_status_message = f"Camera error: {str(e)}"
                self.camera_connected = False

    def update_camera_feed(self, surface=None):
        """Update the camera feed display manually.

        Args:
            surface (pygame.Surface, optional): Camera feed surface
        """
        if surface:
            self.camera_feed = surface
            self.camera_connected = True
            self.last_camera_update = time.time()

    def stop_camera_feed(self):
        """Stop the camera feed and clean up resources."""
        if self.camera_client:
            try:
                print("Stopping camera feed")
                self.camera_client.stop_continuous_frames()
                print("Camera feed stopped")
            except Exception as e:
                print(f"Error stopping camera feed: {e}")

    def close(self):
        """Close the dashboard and clean up resources."""
        # If not already shutting down, show the message
        if not self.shutting_down:
            self.shutting_down = True
            self.shutdown_start_time = time.time()
            # Keep updating for a second to show the shutdown screen
            end_time = time.time() + 1.5
            while time.time() < end_time and self.running:
                self.update()

        # Stop the camera feed
        self.stop_camera_feed()

        self.running = False


class EmojiRenderer:
    """Improved emoji rendering class using freetype."""

    def __init__(self):
        """Initialize the emoji renderer."""
        self.freetype_available = FREETYPE_AVAILABLE
        self.emoji_font = None

        if not self.freetype_available:
            print("Freetype not available, using fallback icons")
            return

        try:
            # Try to find the emoji font based on OS
            emoji_fonts = []

            # macOS emoji font
            if sys.platform == "darwin":
                emoji_fonts.append("/System/Library/Fonts/Apple Color Emoji.ttc")

            # Windows emoji font
            elif sys.platform == "win32":
                emoji_fonts.append("C:\\Windows\\Fonts\\seguiemj.ttf")

            # Linux emoji fonts
            else:
                emoji_fonts.extend(
                    [
                        "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
                        "/usr/share/fonts/noto-emoji/NotoColorEmoji.ttf",
                        "/usr/share/fonts/truetype/noto-emoji/NotoColorEmoji.ttf",
                    ]
                )

            # Try each font until one works
            for font_path in emoji_fonts:
                if os.path.exists(font_path):
                    self.emoji_font = freetype.Face(font_path)
                    # Set a large size for clear emojis
                    if (
                        hasattr(self.emoji_font, "available_sizes")
                        and self.emoji_font.available_sizes
                    ):
                        self.emoji_font.set_char_size(int(self.emoji_font.available_sizes[-1].size))
                    else:
                        self.emoji_font.set_pixel_sizes(32, 32)
                    break

            if not self.emoji_font:
                print("No emoji font found, using fallback icons")
        except Exception as e:
            print(f"Error initializing emoji support: {e}")
            self.freetype_available = False

    def render_emoji(self, emoji_char, size=24):
        """Render emoji character to a pygame surface.

        Args:
            emoji_char: Unicode character for the emoji
            size: Desired size of the emoji in pixels

        Returns:
            pygame.Surface with the rendered emoji
        """
        try:
            if self.freetype_available and self.emoji_font:
                # Load emoji character with color
                self.emoji_font.load_char(emoji_char, freetype.FT_LOAD_COLOR)

                # Get bitmap dimensions
                bitmap = self.emoji_font.glyph.bitmap
                width, height = bitmap.width, bitmap.rows

                if width == 0 or height == 0:
                    raise ValueError("Invalid bitmap dimensions")

                # Check if it's a color bitmap (BGRA format)
                if bitmap.pixel_mode == freetype.FT_PIXEL_MODE_BGRA:
                    # Convert bitmap data to numpy array
                    buffer_data = np.array(bitmap.buffer, dtype=np.uint8).reshape(height, width, 4)
                    # Swap B and R channels (BGRA -> RGBA for pygame)
                    buffer_data[:, :, [0, 2]] = buffer_data[:, :, [2, 0]]
                    # Create pygame surface from buffer
                    surface = pygame.image.frombuffer(
                        buffer_data.flatten(), (width, height), "RGBA"
                    )
                else:
                    # For non-color bitmaps, create a standard surface
                    surface = pygame.Surface((width, height), pygame.SRCALPHA)
                    buffer_data = bytes(bitmap.buffer)
                    for y in range(height):
                        for x in range(width):
                            idx = y * width + x
                            if idx < len(buffer_data):
                                value = buffer_data[idx]
                                surface.set_at((x, y), (255, 255, 255, value))

                # Scale the surface to desired size if needed
                if width != size or height != size:
                    aspect_ratio = width / height
                    if aspect_ratio > 1:
                        new_width = size
                        new_height = int(size / aspect_ratio)
                    else:
                        new_width = int(size * aspect_ratio)
                        new_height = size
                    surface = pygame.transform.smoothscale(surface, (new_width, new_height))

                return surface
            else:
                # Fallback to rendering text with pygame font
                font = pygame.font.SysFont("Arial", int(size * 0.9))
                text_surface = font.render(emoji_char, True, (255, 255, 255))
                return text_surface

        except Exception as e:
            print(f"Error rendering emoji: {e}")
            # Fallback to simple colored square
            surface = pygame.Surface((size, size), pygame.SRCALPHA)
            color_options = [(255, 100, 100), (100, 255, 100), (100, 100, 255), (255, 255, 100)]
            color_idx = hash(emoji_char) % len(color_options)
            pygame.draw.rect(
                surface, color_options[color_idx], (0, 0, size, size), border_radius=size // 4
            )
            return surface
