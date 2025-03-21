"""
MQTT Broker setup utility for Rasptank project.
This module provides functions to set up and configure the MQTT broker
that will facilitate communication between the PC controller and the Rasptank.
"""

import logging
import os
import subprocess
import sys
import time
from typing import Dict, List, Optional, Tuple

# Configure logging
logger = logging.getLogger("MQTTBrokerSetup")

# Default broker configuration
DEFAULT_BROKER_CONFIG = """
# Default configuration for Mosquitto MQTT broker for Rasptank project
#
# Allow anonymous connections (no username/password required)
allow_anonymous true

# Port for MQTT connections
listener 1883

# No persistence
persistence false

# Log settings
log_dest stdout
log_type error
log_type warning
connection_messages true
"""


def check_mosquitto_installed() -> bool:
    """Check if Mosquitto broker is installed.

    Returns:
        bool: True if installed, False otherwise
    """
    try:
        result = subprocess.run(
            ["mosquitto", "-h"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False


def install_mosquitto() -> bool:
    """Install Mosquitto broker on the system.

    Returns:
        bool: True if installation successful, False otherwise
    """
    logger.info("Installing Mosquitto broker...")

    # Determine the package manager based on the platform
    if sys.platform.startswith("linux"):
        # Check for specific distributions
        if os.path.exists("/etc/debian_version"):
            # Debian/Ubuntu
            cmd = ["sudo", "apt-get", "update"]
            subprocess.run(cmd, check=True)
            cmd = ["sudo", "apt-get", "install", "-y", "mosquitto", "mosquitto-clients"]
        elif os.path.exists("/etc/redhat-release"):
            # RHEL/CentOS/Fedora
            cmd = ["sudo", "yum", "install", "-y", "mosquitto", "mosquitto-clients"]
        else:
            logger.error("Unsupported Linux distribution")
            return False
    elif sys.platform == "darwin":
        # macOS
        cmd = ["brew", "install", "mosquitto"]
    elif sys.platform == "win32":
        logger.error("Windows installation not supported through this script")
        logger.error("Please download and install Mosquitto from: https://mosquitto.org/download/")
        return False
    else:
        logger.error(f"Unsupported platform: {sys.platform}")
        return False

    try:
        subprocess.run(cmd, check=True)
        logger.info("Mosquitto installation completed")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install Mosquitto: {e}")
        return False
    except Exception as e:
        logger.error(f"Error installing Mosquitto: {e}")
        return False


def create_config_file(config_path: str = "/tmp/rasptank-mosquitto.conf") -> str:
    """Create a configuration file for Mosquitto.

    Args:
        config_path (str): Path to create the configuration file

    Returns:
        str: Path to the created configuration file
    """
    try:
        with open(config_path, "w") as f:
            f.write(DEFAULT_BROKER_CONFIG)
        logger.info(f"Created Mosquitto configuration file at {config_path}")
        return config_path
    except Exception as e:
        logger.error(f"Error creating Mosquitto configuration file: {e}")
        return ""


def start_broker(config_path: str) -> Optional[subprocess.Popen]:
    """Start the Mosquitto broker with the given configuration.

    Args:
        config_path (str): Path to the Mosquitto configuration file

    Returns:
        subprocess.Popen: Process handle if successful, None otherwise
    """
    try:
        logger.info("Starting Mosquitto broker...")
        process = subprocess.Popen(
            ["mosquitto", "-c", config_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # Wait a moment for the broker to start
        time.sleep(1)

        # Check if the process is still running
        if process.poll() is None:
            logger.info("Mosquitto broker started successfully")
            return process
        else:
            stdout, stderr = process.communicate()
            logger.error(f"Mosquitto broker failed to start: {stderr}")
            return None
    except Exception as e:
        logger.error(f"Error starting Mosquitto broker: {e}")
        return None


def check_broker_status(host: str = "localhost", port: int = 1883) -> bool:
    """Check if the MQTT broker is running and accessible.

    Args:
        host (str): Broker hostname or IP address
        port (int): Broker port

    Returns:
        bool: True if broker is running, False otherwise
    """
    try:
        # Try to run mosquitto_sub with a short timeout
        result = subprocess.run(
            ["mosquitto_sub", "-h", host, "-p", str(port), "-t", "test", "-C", "1", "-W", "2"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )

        # Return code 0 means the command completed successfully
        # (Note: this doesn't guarantee messages can be published/received)
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Error checking broker status: {e}")
        return False


def setup_broker() -> Tuple[bool, Optional[subprocess.Popen]]:
    """Set up the MQTT broker for the Rasptank project.

    This function checks if Mosquitto is installed, installs it if necessary,
    creates a configuration file, and starts the broker.

    Returns:
        Tuple[bool, Optional[subprocess.Popen]]:
            - True if setup was successful, False otherwise
            - Process handle if broker was started, None otherwise
    """
    # Check if Mosquitto is installed
    if not check_mosquitto_installed():
        logger.info("Mosquitto is not installed")
        if not install_mosquitto():
            logger.error("Failed to install Mosquitto")
            return False, None

    # Create configuration file
    config_path = create_config_file()
    if not config_path:
        logger.error("Failed to create Mosquitto configuration file")
        return False, None

    # Check if broker is already running
    if check_broker_status():
        logger.info("MQTT broker is already running")
        return True, None

    # Start broker
    process = start_broker(config_path)
    if process:
        return True, process
    else:
        logger.error("Failed to start MQTT broker")
        return False, None


def main():
    """Main entry point when run as a script."""
    # Configure logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    # Set up broker
    success, process = setup_broker()

    if success:
        logger.info("MQTT broker setup completed successfully")

        if process:
            logger.info("Press Ctrl+C to stop the broker and exit")
            try:
                # Keep the script running while the broker is running
                while process.poll() is None:
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.info("Stopping broker...")
                process.terminate()
                process.wait()
                logger.info("Broker stopped")
    else:
        logger.error("MQTT broker setup failed")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
