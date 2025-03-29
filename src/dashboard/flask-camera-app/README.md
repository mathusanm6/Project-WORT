# Flask Camera App

## Description
Flask Camera App is a simple web application that streams video from a camera using Flask. It is designed to run on Ubuntu and utilizes the camera module to capture images and display them in real-time on a web page.

## Project Structure
```
flask-camera-app
├── src
│   ├── app.py            # Entry point of the Flask application
│   ├── camera.py         # Contains the Camera class for managing camera access
│   └── templates
│       └── index.html    # HTML template for the home page displaying the video stream
├── requirements.txt       # Lists the dependencies required for the project
└── README.md              # Documentation for the project
```

## Requirements
To run this application, you need to have the following dependencies installed:

- Flask
- picamera (if using Raspberry Pi)
- Other necessary libraries as specified in `requirements.txt`

## Installation
1. Clone the repository:
   ```
   git clone <repository-url>
   cd flask-camera-app
   ```

2. Install the required packages:
   ```
   pip install -r requirements.txt
   ```

## Running the Application
1. Navigate to the `src` directory:
   ```
   cd src
   ```

2. Run the application:
   ```
   python app.py
   ```

3. Open your web browser and go to `http://localhost:5000` to view the video stream.

## Usage
- The home page will display the video stream from the camera.
- Ensure that your camera is properly connected and configured before starting the application.

## License
This project is licensed under the MIT License.
