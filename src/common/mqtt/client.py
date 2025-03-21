"""
Reusable MQTT client for both Rasptank and PC controller.
This module provides a consistent interface for MQTT communications.
"""

import logging
import threading
import uuid
from typing import Any, Callable, Optional

import paho.mqtt.client as mqtt

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


class MQTTClient:
    """Base MQTT client class."""

    def __init__(
        self,
        broker_address: str = "192.168.1.200",
        broker_port: int = 1883,
        client_id: str = "",
        keep_alive: int = 60,
        reconnect_delay: int = 5,
    ):
        """Initialize the MQTT client.

        Args:
            broker_address (str): MQTT broker address
            broker_port (int): MQTT broker port
            client_id (str): Client identifier, leave empty for auto-generation
            keep_alive (int): Keep-alive interval in seconds
            reconnect_delay (int): Reconnection delay in seconds
        """
        self.logger = logging.getLogger(f"MQTTClient-{client_id or 'auto'}")

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

    def connect(self) -> bool:
        """Connect to the MQTT broker.

        Returns:
            bool: True if connection was initiated, False otherwise
        """
        try:
            self.logger.info(
                f"Connecting to MQTT broker at {self.broker_address}:{self.broker_port}"
            )
            self.client.connect_async(
                host=self.broker_address,
                port=self.broker_port,
                keepalive=self.keep_alive,
            )
            self.client.loop_start()
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to MQTT broker: {e}")
            return False

    def disconnect(self):
        """Disconnect from the MQTT broker."""
        try:
            self.logger.info("Disconnecting from MQTT broker")
            self.client.loop_stop()
            self.client.disconnect()
            self.connected.clear()
        except Exception as e:
            self.logger.error(f"Error disconnecting from MQTT broker: {e}")

    def wait_for_connection(self, timeout: float = 10.0) -> bool:
        """Wait for connection to be established.

        Args:
            timeout (float): Maximum time to wait in seconds

        Returns:
            bool: True if connected, False if timeout occurred
        """
        return self.connected.wait(timeout=timeout)

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
            self.logger.info(f"Subscribing to topic: {topic}")
            self.client.subscribe(topic, qos)
        else:
            self.logger.warning(f"Cannot subscribe to {topic}: Not connected to broker")

    def unsubscribe(self, topic: str):
        """Unsubscribe from a topic.

        Args:
            topic (str): Topic to unsubscribe from
        """
        if topic in self.topic_handlers:
            del self.topic_handlers[topic]

        if self.connected.is_set():
            self.logger.info(f"Unsubscribing from topic: {topic}")
            self.client.unsubscribe(topic)
        else:
            self.logger.warning(f"Cannot unsubscribe from {topic}: Not connected to broker")

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
            self.logger.warning(f"Cannot publish to {topic}: Not connected to broker")
            return False

        try:
            self.logger.debug(f"Publishing to {topic}: {payload}")
            self.client.publish(topic, payload, qos=qos, retain=retain)
            return True
        except Exception as e:
            self.logger.error(f"Error publishing to {topic}: {e}")
            return False

    def _on_connect(self, client, userdata, flags, rc):
        """Callback for when the client connects to the broker."""
        if rc == 0:
            self.logger.info(f"Connected to MQTT broker (RC={rc})")
            self.connected.set()

            # Resubscribe to all topics
            for topic in self.topic_handlers:
                self.logger.info(f"Resubscribing to topic: {topic}")
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
            self.logger.error(f"Failed to connect to MQTT broker: {error_msg}")

    def _on_disconnect(self, client, userdata, rc):
        """Callback for when the client disconnects from the broker."""
        self.connected.clear()

        if rc == 0:
            self.logger.info("Disconnected from MQTT broker (clean disconnect)")
        else:
            self.logger.warning(f"Unexpected disconnect from MQTT broker (RC={rc})")

    def _on_message(self, client, userdata, msg):
        """Callback for when a message is received from the broker."""
        topic = msg.topic
        try:
            payload = msg.payload.decode("utf-8")
            qos = msg.qos
            retain = msg.retain

            self.logger.debug(f"Received message on {topic}: {payload}")

            # If we have a handler for this topic, call it
            if topic in self.topic_handlers:
                handler = self.topic_handlers[topic]
                handler(self, topic, payload, qos, retain)
        except Exception as e:
            self.logger.error(f"Error handling message on {topic}: {e}")
