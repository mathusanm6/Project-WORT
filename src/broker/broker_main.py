"""
MQTT Broker setup utility for Rasptank project.
This module provides functions to set up and configure the MQTT broker
that will facilitate communication between the PC controller and the Rasptank.
"""

import os
import subprocess
import sys
import time
from typing import Optional, Tuple

from src.common.logging.decorators import log_function_call

# Import from logging system
from src.common.logging.logger_factory import LoggerFactory

# Create logger
logger = LoggerFactory.create_logger(
    logger_type="console", name="RasptankUtil.MQTTBrokerSetup", level="INFO"
)

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
        logger.debugw("Checking if Mosquitto broker is installed")
        result = subprocess.run(
            ["mosquitto", "-h"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        is_installed = result.returncode == 0
        logger.debugw("Mosquitto broker check", "installed", is_installed)
        return is_installed
    except FileNotFoundError:
        logger.debugw("Mosquitto broker not found")
        return False


@log_function_call()
def install_mosquitto() -> bool:
    """Install Mosquitto broker on the system.

    Returns:
        bool: True if installation successful, False otherwise
    """
    logger.infow("Installing Mosquitto broker")

    # Determine the package manager based on the platform
    if sys.platform.startswith("linux"):
        # Check for specific distributions
        if os.path.exists("/etc/debian_version"):
            # Debian/Ubuntu
            logger.debugw("Detected Debian/Ubuntu system")
            cmd = ["sudo", "apt-get", "update"]
            subprocess.run(cmd, check=True)
            cmd = ["sudo", "apt-get", "install", "-y", "mosquitto", "mosquitto-clients"]
        elif os.path.exists("/etc/redhat-release"):
            # RHEL/CentOS/Fedora
            logger.debugw("Detected RHEL/CentOS/Fedora system")
            cmd = ["sudo", "yum", "install", "-y", "mosquitto", "mosquitto-clients"]
        else:
            logger.errorw("Unsupported Linux distribution")
            return False
    elif sys.platform == "darwin":
        # macOS
        logger.debugw("Detected macOS system")
        cmd = ["brew", "install", "mosquitto"]
    elif sys.platform == "win32":
        logger.errorw("Windows installation not supported through this script")
        logger.errorw("Please download and install Mosquitto from: https://mosquitto.org/download/")
        return False
    else:
        logger.errorw("Unsupported platform", "platform", sys.platform)
        return False

    try:
        logger.debugw("Executing installation command", "command", " ".join(cmd))
        subprocess.run(cmd, check=True)
        logger.infow("Mosquitto installation completed successfully")
        return True
    except subprocess.CalledProcessError as e:
        logger.errorw(
            "Failed to install Mosquitto",
            "error",
            str(e),
            "returncode",
            e.returncode,
            exc_info=True,
        )
        return False
    except (PermissionError, OSError) as e:
        logger.errorw("Error installing Mosquitto", "error", str(e), exc_info=True)
        return False


def create_config_file(config_path: str = "/tmp/rasptank-mosquitto.conf") -> str:
    """Create a configuration file for Mosquitto.

    Args:
        config_path (str): Path to create the configuration file

    Returns:
        str: Path to the created configuration file
    """
    try:
        logger.debugw("Creating Mosquitto configuration file", "path", config_path)
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(DEFAULT_BROKER_CONFIG)
        logger.infow("Created Mosquitto configuration file", "path", config_path)
        return config_path
    except (IOError, OSError, PermissionError) as e:
        logger.errorw(
            "Error creating Mosquitto configuration file",
            "path",
            config_path,
            "error",
            str(e),
            exc_info=True,
        )
        return ""


@log_function_call()
def start_broker(config_path: str) -> Optional[subprocess.Popen]:
    """Start the Mosquitto broker with the given configuration.

    Args:
        config_path (str): Path to the Mosquitto configuration file

    Returns:
        subprocess.Popen: Process handle if successful, None otherwise
    """
    try:
        logger.infow("Starting Mosquitto broker", "config", config_path)

        # pylint: disable=consider-using-with  # Resource management handled by caller
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
            logger.infow("Mosquitto broker started successfully", "pid", process.pid)
            return process

        # The process didn't start successfully
        _, stderr = process.communicate()
        logger.errorw(
            "Mosquitto broker failed to start",
            "return_code",
            process.returncode,
            "stderr",
            stderr,
        )
        return None
    except (FileNotFoundError, PermissionError, subprocess.SubprocessError, OSError) as e:
        logger.errorw("Error starting Mosquitto broker", "error", str(e), exc_info=True)
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
        logger.debugw("Checking MQTT broker status", "host", host, "port", port)

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
        is_running = result.returncode == 0
        logger.debugw("MQTT broker status check", "running", is_running)
        return is_running
    except (FileNotFoundError, subprocess.SubprocessError, ConnectionError, OSError) as e:
        logger.errorw(
            "Error checking broker status",
            "host",
            host,
            "port",
            port,
            "error",
            str(e),
            exc_info=True,
        )
        return False


@log_function_call()
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
        logger.infow("Mosquitto is not installed, attempting installation")
        if not install_mosquitto():
            logger.errorw("Failed to install Mosquitto")
            return False, None

    # Create configuration file
    config_path = create_config_file()
    if not config_path:
        logger.errorw("Failed to create Mosquitto configuration file")
        return False, None

    # Check if broker is already running
    if check_broker_status():
        logger.infow("MQTT broker is already running")
        return True, None

    # Start broker
    process = start_broker(config_path)
    if process:
        return True, process

    logger.errorw("Failed to start MQTT broker")
    return False, None


def main():
    """Main entry point when run as a script."""
    logger.infow("Starting MQTT broker setup utility")

    # Set up broker
    success, process = setup_broker()

    if success:
        logger.infow("MQTT broker setup completed successfully")
        if process:
            logger.infow("Press Ctrl+C to stop the broker and exit")
            try:
                # Keep the script running while the broker is running
                while process.poll() is None:
                    time.sleep(1)
            except KeyboardInterrupt:
                logger.infow("Stopping broker...")
                process.terminate()
                process.wait()
                logger.infow("Broker stopped")
    else:
        logger.errorw("MQTT broker setup failed")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
