import time

import cv2


class Camera:
    def __init__(self):
        # Initialisation de la capture vidéo (index 0 pour la webcam par défaut)
        self.video = cv2.VideoCapture(0)
        if not self.video.isOpened():
            raise RuntimeError("Impossible d'accéder à la caméra.")

        # Variables pour le calcul des FPS
        self.prev_time = time.time()
        self.frame_count = 0
        self.fps = 0

    def __del__(self):
        # Libération de la caméra
        self.video.release()

    def get_frame(self):
        # Lecture d'une image depuis la caméra
        success, frame = self.video.read()
        if not success:
            raise RuntimeError("Impossible de lire une image depuis la caméra.")

        # Calcul des FPS
        self.frame_count += 1
        current_time = time.time()
        elapsed_time = current_time - self.prev_time
        if elapsed_time >= 1.0:  # Mettre à jour les FPS toutes les secondes
            self.fps = self.frame_count / elapsed_time
            self.frame_count = 0
            self.prev_time = current_time

        # Ajouter les FPS sur l'image
        cv2.putText(
            frame, f"FPS: {self.fps:.2f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2
        )

        # Encodage de l'image en JPEG
        _, jpeg = cv2.imencode(".jpg", frame)
        return jpeg.tobytes()


def gen(camera):
    """Fonction génératrice pour le streaming vidéo."""
    yield b"--frame\r\n"
    while True:
        try:
            frame = camera.get_frame()
            yield b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n--frame\r\n"
        except RuntimeError as e:
            print(f"Erreur : {e}")
            break
