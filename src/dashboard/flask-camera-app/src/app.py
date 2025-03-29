#!/usr/bin/env python
import os

from camera import Camera
from flask import Flask, Response, render_template

app = Flask(__name__)


@app.route("/")
def index():
    """Page d'accueil pour le streaming vidéo."""
    return render_template("index.html")


def gen(camera):
    """Fonction génératrice pour le streaming vidéo."""
    yield b"--frame\r\n"
    while True:
        frame = camera.get_frame()
        yield b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n--frame\r\n"


@app.route("/video_feed")
def video_feed():
    """Route pour le flux vidéo. À utiliser dans l'attribut src d'une balise img."""
    return Response(gen(Camera()), mimetype="multipart/x-mixed-replace; boundary=frame")


if __name__ == "__main__":
    # Lancer le serveur Flask sur toutes les interfaces réseau (0.0.0.0)
    # Cela permet à d'autres appareils sur le même réseau d'accéder au flux
    app.run(host="0.0.0.0", port=5000, threaded=True)
