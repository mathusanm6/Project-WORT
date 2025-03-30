#!/usr/bin/env python3
"""
High Performance Camera Client for Rasptank

This module provides an optimized client for interacting with the Rasptank camera server,
focusing on maximum frame rate and minimal latency for real-time video feeds.
"""

import io
import queue
import threading
import time
import urllib.request
from typing import Callable, List, Optional, Tuple

import numpy as np
import pygame


class CameraClient:
    """
    High performance client for the Rasptank camera server.

    Features:
    - Multi-threaded frame fetching for maximum throughput
    - Adaptive frame rate based on network conditions
    - Minimal processing overhead
    - Efficient thread synchronization
    """

    def __init__(
        self,
        server_url: str = "http://100.127.187.15:5000",
        target_fps: int = 30,
        num_fetch_threads: int = 2,
        max_queue_size: int = 3,
        timeout: float = 0.3,
        enable_logging: bool = False,
    ):
        """
        Initialize the high performance camera client.

        Args:
            server_url: URL of the camera server
            target_fps: Target frames per second
            num_fetch_threads: Number of parallel fetching threads
            max_queue_size: Maximum size of frame queue
            timeout: Timeout for HTTP requests
            enable_logging: Whether to print debug logs
        """
        # Configuration
        self.server_url = server_url
        self.target_fps = target_fps
        self.frame_interval = 1.0 / target_fps
        self.num_fetch_threads = num_fetch_threads
        self.timeout = timeout
        self.logging = enable_logging

        # State variables
        self.running = False
        self.connected = False
        self.last_connection_check = 0
        self.last_successful_frame = 0
        self.frames_received = 0
        self.connection_errors = 0
        self.frame_processing_errors = 0

        # Performance metrics
        self.actual_fps = 0
        self.network_latency = 0
        self.processing_time = 0
        self._fps_update_time = 0
        self._fps_frame_count = 0

        # Frame storage
        self.latest_frame_bytes = None
        self.latest_frame_time = 0
        self.latest_surface = None
        self.latest_surface_time = 0

        # Multi-threading components
        self.frame_queue = queue.Queue(maxsize=max_queue_size)
        self.stop_event = threading.Event()
        self.fetch_threads = []
        self.process_thread = None

        # QR code data
        self.latest_qr_codes = []
        self.latest_qr_time = 0

        # Try initial connection
        self._check_connection()

    def _log(self, message: str) -> None:
        """Print a log message if logging is enabled."""
        if self.logging:
            print(f"[CameraClient] {message}")

    def _check_connection(self) -> bool:
        """Check connection to camera server."""
        now = time.time()

        # Don't check too frequently
        if now - self.last_connection_check < 3.0 and self.connected:
            return self.connected

        self.last_connection_check = now

        try:
            # Fast HEAD request to check if server is available
            request = urllib.request.Request(f"{self.server_url}/health", method="HEAD")
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                self.connected = response.status == 200

                if self.connected:
                    self.connection_errors = 0
                    self._log(f"Connected to camera server at {self.server_url}")
                else:
                    self.connection_errors += 1
                    self._log(f"Server returned non-200 status: {response.status}")

                return self.connected

        except Exception as e:
            self.connected = False
            self.connection_errors += 1
            if self.connection_errors <= 1 or self.connection_errors % 10 == 0:
                self._log(f"Connection error: {str(e)}")
            return False

    def _fetch_frames_worker(self) -> None:
        """Worker thread that continuously fetches frames from the server."""
        thread_id = threading.get_ident()
        self._log(f"Frame fetch thread {thread_id} started")

        consecutive_errors = 0

        while not self.stop_event.is_set():
            if self.frame_queue.full():
                # If queue is full, wait a bit to avoid consuming CPU
                time.sleep(self.frame_interval / 4)
                continue

            # Check if we need to reconnect
            if not self.connected and consecutive_errors % 5 == 0:
                self._check_connection()

            if not self.connected:
                consecutive_errors += 1
                time.sleep(min(1.0, consecutive_errors * 0.1))
                continue

            try:
                # Time the request for latency calculation
                start_time = time.time()

                # Fetch a new frame
                with urllib.request.urlopen(
                    f"{self.server_url}/latest_frame", timeout=self.timeout
                ) as response:
                    if response.status == 200:
                        # Read frame data
                        frame_data = response.read()

                        # Calculate network latency
                        self.network_latency = time.time() - start_time

                        # Add to queue if not full (non-blocking)
                        try:
                            self.frame_queue.put_nowait((time.time(), frame_data))
                            consecutive_errors = 0
                        except queue.Full:
                            # Queue is full, just continue
                            pass
                    else:
                        consecutive_errors += 1
                        if consecutive_errors <= 3:
                            self._log(f"Server returned status: {response.status}")

            except Exception as e:
                consecutive_errors += 1
                if consecutive_errors <= 3 or consecutive_errors % 10 == 0:
                    self._log(f"Error fetching frame: {str(e)}")

                # Adjust connection status
                if consecutive_errors >= 3:
                    self.connected = False

            # Adaptive frame rate based on network conditions
            # If network is slow, don't try to fetch too frequently
            sleep_time = max(
                0.001,  # Minimum sleep to avoid CPU spinning
                self.frame_interval - self.network_latency,
            )

            # Use shorter sleep periods while checking for stop event
            sleep_until = time.time() + sleep_time
            while time.time() < sleep_until and not self.stop_event.is_set():
                time.sleep(0.01)

        self._log(f"Frame fetch thread {thread_id} stopped")

    def _process_frames_worker(self) -> None:
        """Worker thread that processes frames from the queue."""
        self._log("Frame processing thread started")

        while not self.stop_event.is_set():
            try:
                # Get frame from queue with timeout
                try:
                    frame_time, frame_data = self.frame_queue.get(timeout=0.1)
                except queue.Empty:
                    continue

                # Store the frame
                self.latest_frame_bytes = frame_data
                self.latest_frame_time = frame_time
                self.last_successful_frame = time.time()
                self.frames_received += 1

                # Update FPS counter
                now = time.time()
                self._fps_frame_count += 1

                if now - self._fps_update_time >= 1.0:
                    self.actual_fps = self._fps_frame_count / (now - self._fps_update_time)
                    self._fps_update_time = now
                    self._fps_frame_count = 0

                    # Log stats occasionally
                    if self.logging and self.frames_received % 30 == 0:
                        self._log(
                            f"Stats: FPS={self.actual_fps:.1f}, "
                            + f"Latency={self.network_latency*1000:.1f}ms, "
                            + f"Queue={self.frame_queue.qsize()}/{self.frame_queue.maxsize}"
                        )

                # Mark task as done
                self.frame_queue.task_done()

            except Exception as e:
                self.frame_processing_errors += 1
                if self.frame_processing_errors <= 5 or self.frame_processing_errors % 20 == 0:
                    self._log(f"Error processing frame: {str(e)}")

        self._log("Frame processing thread stopped")

    def start_continuous_frames(self) -> None:
        """Start continuous frame fetching."""
        if self.running:
            self._log("Already running")
            return

        self.stop_event.clear()
        self.running = True

        # Create and start fetch threads
        self.fetch_threads = []
        for i in range(self.num_fetch_threads):
            thread = threading.Thread(target=self._fetch_frames_worker, daemon=True)
            thread.start()
            self.fetch_threads.append(thread)

        # Create and start process thread
        self.process_thread = threading.Thread(target=self._process_frames_worker, daemon=True)
        self.process_thread.start()

        self._log(f"Started {self.num_fetch_threads} fetch threads and 1 process thread")
        self._fps_update_time = time.time()
        self._fps_frame_count = 0

    def stop_continuous_frames(self) -> None:
        """Stop continuous frame fetching."""
        if not self.running:
            return

        self._log("Stopping frame fetching")
        self.stop_event.set()
        self.running = False

        # Wait for threads to finish (with timeout)
        for thread in self.fetch_threads:
            thread.join(timeout=0.5)

        if self.process_thread:
            self.process_thread.join(timeout=0.5)

        # Clear queue
        while not self.frame_queue.empty():
            try:
                self.frame_queue.get_nowait()
                self.frame_queue.task_done()
            except:
                pass

        self.fetch_threads = []
        self.process_thread = None
        self._log("Frame fetching stopped")

    def get_frame_as_pygame_surface(
        self, max_age_seconds: float = 0.1, scale_to: Optional[Tuple[int, int]] = None
    ) -> Optional[pygame.Surface]:
        """
        Get the latest camera frame as a Pygame surface.

        Args:
            max_age_seconds: Maximum age of frame to return
            scale_to: Optional (width, height) to scale the surface to

        Returns:
            pygame.Surface or None if no frame is available
        """
        now = time.time()

        # Check if we need a new surface based on frame timestamp
        frame_age = now - self.latest_frame_time
        surface_age = now - self.latest_surface_time

        need_new_surface = (
            self.latest_surface is None
            or frame_age <= max_age_seconds
            and self.latest_frame_time > self.latest_surface_time
        )

        # Return existing surface if it's fresh enough
        if self.latest_surface and not need_new_surface:
            # If scale requested and different from current
            if scale_to and self.latest_surface.get_size() != scale_to:
                try:
                    return pygame.transform.smoothscale(self.latest_surface, scale_to)
                except:
                    return self.latest_surface
            return self.latest_surface

        # Get latest frame
        if not self.latest_frame_bytes or frame_age > max_age_seconds:
            # If no continuous fetching, try once
            if not self.running and self._check_connection():
                try:
                    with urllib.request.urlopen(
                        f"{self.server_url}/latest_frame", timeout=self.timeout
                    ) as response:
                        if response.status == 200:
                            self.latest_frame_bytes = response.read()
                            self.latest_frame_time = time.time()
                except:
                    pass

            # Still no frame available
            if not self.latest_frame_bytes or now - self.latest_frame_time > max_age_seconds:
                return self.latest_surface

        # Convert bytes to surface
        try:
            # Measure processing time
            start_time = time.time()

            # Load image from bytes
            image_stream = io.BytesIO(self.latest_frame_bytes)
            new_surface = pygame.image.load(image_stream)

            # Scale if requested
            if scale_to:
                new_surface = pygame.transform.smoothscale(new_surface, scale_to)

            # Store for future reuse
            self.latest_surface = new_surface
            self.latest_surface_time = time.time()

            # Update processing time metric
            self.processing_time = time.time() - start_time

            return new_surface

        except Exception as e:
            self.frame_processing_errors += 1
            if self.frame_processing_errors <= 5 or self.frame_processing_errors % 20 == 0:
                self._log(f"Error creating Pygame surface: {str(e)}")
            return self.latest_surface

    def read_qr_codes(self, force_refresh: bool = False) -> List[str]:
        """
        Read QR codes from the camera.

        Args:
            force_refresh: If True, fetch fresh data from server

        Returns:
            List of detected QR code strings
        """
        now = time.time()

        # Return cached QR codes if fresh enough
        if not force_refresh and self.latest_qr_codes and now - self.latest_qr_time < 1.0:
            return self.latest_qr_codes

        # Don't try if not connected
        if not self.connected and not self._check_connection():
            return self.latest_qr_codes

        try:
            with urllib.request.urlopen(
                f"{self.server_url}/read_qr", timeout=self.timeout * 2
            ) as response:
                if response.status == 200:
                    import json

                    data = json.loads(response.read().decode("utf-8"))

                    if data.get("success", False):
                        self.latest_qr_codes = data.get("qr_codes", [])
                        self.latest_qr_time = now

                        if self.latest_qr_codes and self.logging:
                            self._log(f"QR codes detected: {self.latest_qr_codes}")

                        return self.latest_qr_codes
        except:
            pass

        return self.latest_qr_codes

    def get_stats(self) -> dict:
        """Get performance statistics."""
        return {
            "fps": self.actual_fps,
            "latency_ms": self.network_latency * 1000,
            "processing_ms": self.processing_time * 1000,
            "queue_size": self.frame_queue.qsize() if self.running else 0,
            "queue_capacity": self.frame_queue.maxsize,
            "frames_received": self.frames_received,
            "connection_errors": self.connection_errors,
            "processing_errors": self.frame_processing_errors,
            "connected": self.connected,
            "running": self.running,
            "server_url": self.server_url,
        }

    def cleanup(self) -> None:
        """Clean up resources."""
        self.stop_continuous_frames()

        # Release memory
        self.latest_frame_bytes = None
        self.latest_surface = None
        self.latest_qr_codes = []

        self._log("Resources cleaned up")

    def change_server_url(self, new_url: str) -> None:
        """
        Change the camera server URL.

        Args:
            new_url: New camera server URL
        """
        self._log(f"Changing server URL from {self.server_url} to {new_url}")

        # Stop continuous fetching if active
        was_running = self.running
        if was_running:
            self.stop_continuous_frames()

        # Update URL and reset connection state
        self.server_url = new_url
        self.connected = False
        self.last_connection_check = 0

        # Check connection to new server
        self._check_connection()

        # Restart if it was running before
        if was_running:
            self.start_continuous_frames()
