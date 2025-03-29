"""
Reusable MQTT client for both Rasptank and PC controller.
This module provides a consistent interface for MQTT communications.
"""

import threading
import uuid
from typing import Any, Callable, Optional

import paho.mqtt.client as mqtt

from src.common.logging.decorators import log_function_call
from src.common.logging.logger_api import Logger


class MQTTClient:
    """Base MQTT client class."""

    def __init__(
        self,
        mqtt_logger: Logger,
        broker_address: str = "192.168.1.200",
        broker_port: int = 1883,
        client_id: str = "",
        keep_alive: int = 60,
        reconnect_delay: int = 5,
    ):
        """Initialize the MQTT client.

        Args:
            mqtt_logger (Logger): Logger instance for MQTT client
            broker_address (str): MQTT broker address
            broker_port (int): MQTT broker port
            client_id (str): Client identifier, leave empty for auto-generation
            keep_alive (int): Keep-alive interval in seconds
            reconnect_delay (int): Reconnection delay in seconds
        """
        self.logger = mqtt_logger

        self.logger.infow("Initializing MQTT client", "broker", broker_address, "port", broker_port)

        # MQTT configuration
        self.broker_address = broker_address
        self.broker_port = broker_port
        self.client_id = client_id or f"mqttclient-{uuid.uuid4().hex[:8]}"
        self.keep_alive = keep_alive
        self.reconnect_delay = reconnect_delay

        # Connection state
        self.connected = threading.Event()

        # Topic callbacks
        self.topic_handlers = {}

        # Initialize client
        self.client = mqtt.Client(client_id=self.client_id)
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        # Automatic reconnection
        self.client.reconnect_delay_set(min_delay=1, max_delay=reconnect_delay)

        self.logger.debugw(
            "MQTT client initialized",
            "client_id",
            self.client_id,
            "keep_alive",
            keep_alive,
            "reconnect_delay",
            reconnect_delay,
        )

    @log_function_call()
    def connect(self) -> bool:
        """Connect to the MQTT broker.

        Returns:
            bool: True if connection was initiated, False otherwise
        """
        try:
            self.logger.infow(
                "Connecting to MQTT broker", "broker", self.broker_address, "port", self.broker_port
            )

            self.client.connect_async(
                host=self.broker_address,
                port=self.broker_port,
                keepalive=self.keep_alive,
            )
            self.client.loop_start()
            return True
        except Exception as e:
            self.logger.errorw("Failed to connect to MQTT broker", "error", str(e), exc_info=True)
            return False

    def disconnect(self):
        """Disconnect from the MQTT broker."""
        try:
            self.logger.infow("Disconnecting from MQTT broker")
            self.client.loop_stop()
            self.client.disconnect()
            self.connected.clear()
        except Exception as e:
            self.logger.errorw(
                "Error disconnecting from MQTT broker", "error", str(e), exc_info=True
            )

    def wait_for_connection(self, timeout: float = 10.0) -> bool:
        """Wait for connection to be established.

        Args:
            timeout (float): Maximum time to wait in seconds

        Returns:
            bool: True if connected, False if timeout occurred
        """
        result = self.connected.wait(timeout=timeout)
        if result:
            self.logger.debugw("Successfully connected to MQTT broker", "timeout_value", timeout)
        else:
            self.logger.warnw("Connection timeout to MQTT broker", "timeout_value", timeout)
        return result

    def subscribe(self, topic: str, qos: int = 0, callback: Optional[Callable] = None):
        """Subscribe to a topic.

        Args:
            topic (str): Topic to subscribe to
            qos (int): Quality of Service level
            callback (callable): Function to call when a message is received on this topic.
                                Function signature should be callback(client, topic, payload, qos, retain)
        """
        if callback:
            self.topic_handlers[topic] = callback

        if self.connected.is_set():
            self.logger.infow("Subscribing to topic", "topic", topic, "qos", qos)
            self.client.subscribe(topic, qos)
        else:
            self.logger.warnw("Cannot subscribe to topic: Not connected", "topic", topic)

    def unsubscribe(self, topic: str):
        """Unsubscribe from a topic.

        Args:
            topic (str): Topic to unsubscribe from
        """
        if topic in self.topic_handlers:
            del self.topic_handlers[topic]

        if self.connected.is_set():
            self.logger.infow("Unsubscribing from topic", "topic", topic)
            self.client.unsubscribe(topic)
        else:
            self.logger.warnw("Cannot unsubscribe from topic: Not connected", "topic", topic)

    def publish(self, topic: str, payload: str, qos: int = 0, retain: bool = False) -> bool:
        """Publish a message to a topic.

        Args:
            topic (str): Topic to publish to
            payload (str): Message payload
            qos (int): Quality of Service level
            retain (bool): Whether the message should be retained

        Returns:
            bool: True if publish initiated, False otherwise
        """
        if not self.connected.is_set():
            self.logger.warnw("Cannot publish: Not connected", "topic", topic)
            return False

        try:
            self.logger.debugw(
                "Publishing message",
                "topic",
                topic,
                "payload",
                payload,
                "qos",
                qos,
                "retain",
                retain,
            )

            self.client.publish(topic, payload, qos=qos, retain=retain)
            return True
        except Exception as e:
            self.logger.errorw(
                "Error publishing message", "topic", topic, "error", str(e), exc_info=True
            )
            return False

    def _on_connect(self, client, userdata, flags, rc):
        """Callback for when the client connects to the broker."""
        if rc == 0:
            self.logger.infow("Connected to MQTT broker", "rc", rc, "client_id", self.client_id)
            self.connected.set()

            # Resubscribe to all topics
            for topic in self.topic_handlers:
                self.logger.debugw("Resubscribing to topic", "topic", topic)
                self.client.subscribe(topic)
        else:
            connection_results = {
                1: "Connection refused - incorrect protocol version",
                2: "Connection refused - invalid client identifier",
                3: "Connection refused - server unavailable",
                4: "Connection refused - bad username or password",
                5: "Connection refused - not authorized",
            }
            error_msg = connection_results.get(rc, f"Unknown error code: {rc}")
            self.logger.errorw(
                "Failed to connect to MQTT broker",
                "rc",
                rc,
                "error",
                error_msg,
                "client_id",
                self.client_id,
            )

    def _on_disconnect(self, client, userdata, rc):
        """Callback for when the client disconnects from the broker."""
        self.connected.clear()

        if rc == 0:
            self.logger.infow(
                "Disconnected from MQTT broker (clean disconnect)", "client_id", self.client_id
            )
        else:
            self.logger.warnw(
                "Unexpected disconnect from MQTT broker", "rc", rc, "client_id", self.client_id
            )

    def _on_message(self, client, userdata, msg):
        """Callback for when a message is received from the broker."""
        topic = msg.topic
        try:
            payload = msg.payload.decode("utf-8")
            qos = msg.qos
            retain = msg.retain

            self.logger.debugw(
                "Received message", "topic", topic, "payload", payload, "qos", qos, "retain", retain
            )

            # If we have a handler for this topic, call it
            if topic in self.topic_handlers:
                handler = self.topic_handlers[topic]
                handler(self, topic, payload, qos, retain)
        except Exception as e:
            self.logger.errorw(
                "Error handling message", "topic", topic, "error", str(e), exc_info=True
            )
