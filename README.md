# Network Programming Project - M1 IoT (2024-2025)

## Overview

This project aims to program a small robot to participate in the *World of Rasptank* game.

### *World of Rasptank*

<p align="center">
  <img src="resources/images/world_of_rasptank.jpeg" alt="World of Rasptank (AI GENERATED)" width="860px">
  <legend>World of Rasptank</legend>
</p>

This game involves two teams: a blue team and a red team. Participants are evenly split between the two teams. Each team has a base. The objective is to capture the flag placed in the center of the field and bring it back to your base.

To capture the flag, you must stay in the capture zone for 5 seconds.

:warning: **Important**:

- If you are carrying the flag and get hit, you drop it. The flag then automatically returns to the capture zone.
- If you are hit while capturing the flag, the capture is canceled. You must leave the zone and re-enter it to restart the capture process.

To deposit the flag in your base, scan the QR code located there. A team wins the game by bringing three flags back to their base.

## Context

We had to work in trios and had been provided with a “Rasptank”, a small tracked robot controlled via a Raspberry Pi.

<p align="center">
  <img src="resources/images/rasptank.png" width="400px">
  <legend>Adeept Rasptank</legend>
</p>

## Objectives

The final evaluation will take the form of a World of Rasptank match. Therefore, it is essential to have a fully operational robot by the end of the course.

## Our Achievements

We have successfully completed the project, and our robot is fully functional. We have implemented all the required features and even added some additional functionalities.

#### Rasptank

- [x] Remotely controllable
- [x] Movement in all directions
- [x] Three speed modes: slow, medium, and fast
- [x] Three turning types: curve, spin and pivot
- [x] Shooting via an infrared emitter
- [x] Detection of hits through an infrared receiver, resulting in tank immobilization for 2 seconds and orange LED blinking.
- [x] Detection of entry into the capture zone (white area) using the line-following module.
- [x] Real-time streaming of webcam video feed*.

(*): The webcam streaming wasn't required but recommended. We did it to enhance our experience and for fun.

#### Controller (a.k.a Dashboard in our case)

We had complete freedom in designing the controller, but it had to allow at least:

- Sending commands to the Rasptank (movements, shots, etc.).
- Viewing the webcam stream.

<p align="center">
  <img src="course-materials/documentation/images/controller_tk.gif" width="400px">
  <legend>A basic example of the controller</legend>
</p>

We chose to create a graphical interface using `pygame`, which runs on a separate computer and connects to a PS5 DualSense controller either via Bluetooth or a wired connection.

- [x] Sending commands to the Rasptank
- [x] Displaying the webcam stream directly in the interface
- [x] Displaying the Rasptank-related information (battery level, speed, etc.)
- [x] Displaying the DualSense controller information (connection status, feedback status, etc.)
- [x] Displaying in-game information (flag status, capture zone status, etc.)
- [x] Displaying the game status (game in progress, game over, etc.)


## Contributors

| First Name | Last Name  | GitHub ID   |
| ---------- | ---------- | ----------- |
| Jewin      | CHENG      | @jewinc     |
| Elie       | KANGA      | @Kg-elie    |
| Mathusan   | SELVAKUMAR | @mathusanm6 |
