#!/usr/bin/python3
# File name : setup.py
# Author : Modified from Adeept's original

"""This script sets up the Raspberry Pi for the Adeept RaspTank project.
It installs necessary system dependencies and Python packages in a virtual environment."""

import argparse
import os
import subprocess
import sys
import time

curpath = os.path.realpath(__file__)
thisPath = "/" + os.path.dirname(curpath)
project_root = os.path.dirname(curpath)  # This is Project-WORT folder

# Parse command-line arguments
parser = argparse.ArgumentParser(description="Setup script for RaspTank project.")
parser.add_argument(
    "--no-reboot", action="store_true", help="Disable automatic reboot after setup."
)
args = parser.parse_args()


def replace_num(file, initial, new_num):
    newline = ""
    str_num = str(new_num)
    with open(file, "r") as f:
        for line in f.readlines():
            if line.find(initial) == 0:
                line = str_num + "\n"
            newline += line
    with open(file, "w") as f:
        f.writelines(newline)


def run_with_retry(command, retries=3):
    """Run a command with retries"""
    for attempt in range(retries):
        try:
            print(f"Running: {command}")
            result = subprocess.run(command, shell=True, check=True)
            return True
        except subprocess.CalledProcessError:
            print(f"Error executing: {command}, attempt {attempt+1}/{retries}")
            if attempt == retries - 1:
                return False
            time.sleep(1)  # Short delay before retry


# Step 1: Free up space by removing unnecessary packages
space_saving_commands = [
    "sudo apt-get update",
    "sudo apt-get purge -y wolfram-engine",
    "sudo apt-get purge -y libreoffice*",
    "sudo apt-get -y clean",
    "sudo apt-get -y autoremove",
]

print("Step 1: Freeing up space...")
for command in space_saving_commands:
    run_with_retry(command)

# Create virtual environment
venv_path = os.path.join(project_root, "venv")
print(f"Creating virtual environment at {venv_path}...")
subprocess.run([sys.executable, "-m", "venv", venv_path])

# Get paths to pip and python in the virtual environment
if os.name == "nt":  # Windows
    venv_python = os.path.join(venv_path, "Scripts", "python.exe")
    venv_pip = os.path.join(venv_path, "Scripts", "pip.exe")
else:  # Unix/Linux
    venv_python = os.path.join(venv_path, "bin", "python")
    venv_pip = os.path.join(venv_path, "bin", "pip")

# Upgrade pip in the virtual environment
subprocess.run([venv_pip, "install", "--upgrade", "pip"])

# Install system-level dependencies
system_deps = [
    "sudo apt-get install -y python3-venv python3-dev python3-pip libfreetype6-dev libjpeg-dev build-essential",
    "sudo apt-get install -y i2c-tools python3-smbus",
    "sudo apt-get install -y libatlas-base-dev",
    "sudo apt-get install -y libgstreamer1.0-0",
    "sudo apt-get install -y libhdf5-dev",
]

print("Step 2: Installing system dependencies...")
for command in system_deps:
    run_with_retry(command)

# Install Python packages inside the virtual environment
python_packages = [
    "RPi.GPIO",
    "adafruit-pca9685",
    "rpi_ws281x",
    "mpu6050-raspberrypi",
    "flask",
    "flask_cors",
    "websockets",
    "luma.oled",  # Re-added from original
    "numpy",
    "imutils",
    "zmq",
    "pybase64",
    "psutil",
    "opencv-python",
    "paho-mqtt",
    "pygame",
    "pyzbar",
    "pyqrcode",
]

print("Step 3: Installing Python packages...")
# Upgrade setuptools and wheel first to help with installations
print("Upgrading setuptools and wheel...")
subprocess.run([venv_pip, "install", "--upgrade", "setuptools", "wheel"], check=False)

# Give installation process more time and show output
for package in python_packages:
    print(f"Installing {package} in virtual environment...")
    success = False
    for attempt in range(3):  # Retry up to 3 times
        try:
            # Adding timeout and capture_output=False for better visibility of long-running processes
            result = subprocess.run(
                [venv_pip, "install", package], timeout=300, capture_output=False, check=False
            )
            if result.returncode == 0:
                success = True
                break
            print(f"Error installing {package}, attempt {attempt+1}/3")
        except subprocess.TimeoutExpired:
            print(f"Installation of {package} timed out after 5 minutes, attempt {attempt+1}/3")
        except Exception as e:
            print(f"Error installing {package}: {e}, attempt {attempt+1}/3")

    if not success:
        print(f"Failed to install {package} after 3 attempts - continuing anyway")

# Attempt to fix I2C and camera config
try:
    replace_num("/boot/config.txt", "#dtparam=i2c_arm=on", "dtparam=i2c_arm=on\nstart_x=1\n")
    print("Successfully updated boot config for I2C and camera")
except:
    print("Error updating boot config to enable i2c. Please try again manually.")

# Fix conflict with onboard Raspberry Pi audio (from original script)
try:
    print("Configuring audio settings...")
    os.system("sudo touch /etc/modprobe.d/snd-blacklist.conf")
    with open("/etc/modprobe.d/snd-blacklist.conf", "w") as file_to_write:
        file_to_write.write("blacklist snd_bcm2835")
    print("Successfully blacklisted onboard audio")
except:
    print("Failed to configure audio settings")

# Create activation script for convenience
activate_script = os.path.join(project_root, "activate_env.sh")
with open(activate_script, "w") as f:
    f.write(
        f"""#!/bin/bash
source {os.path.join(venv_path, "bin", "activate")}
echo "Virtual environment activated. You can now run your project commands."
"""
    )

os.chmod(activate_script, 0o755)

print(
    """
Setup completed!

The program in Raspberry Pi has been installed.
You can now power off the Raspberry Pi to install the camera and driver board (Robot HAT).
After turning on again, the Raspberry Pi will automatically run the program to set the servos
port signal to turn the servos to the middle position, which is convenient for mechanical assembly.

To activate the virtual environment manually in the future, run:
    source ./activate_env.sh
"""
)

if not args.no_reboot:
    user_input = input("Do you want to reboot the system now? (yes/no): ").strip().lower()
    if user_input == "yes":
        print("Rebooting system in 5 seconds...")
        time.sleep(5)
        os.system("sudo reboot")
    else:
        print("Reboot canceled. Please reboot the system manually to apply changes.")
else:
    print("Automatic reboot disabled. Please reboot the system manually to apply changes.")
