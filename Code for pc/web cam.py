
from flask import Flask, Response, render_template_string
import cv2

# === Настройки ===
PORT = 8000           # порт сервера (http://localhost:8000)
CAM_INDEX = 0         # 0 — первая камера, 1 — вторая и т.д.
JPEG_QUALITY = 80     # качество сжатия (0–100)

# === Инициализация ===
app = Flask(__name__)
cap = cv2.VideoCapture(CAM_INDEX)

if not cap.isOpened():
    raise SystemExit("❌ Камера не обнаружена. Проверь подключение и CAM_INDEX.")

# HTML-страница для браузера
HTML_PAGE = """
<!doctype html>
<meta charset="utf-8">
<title>Live Camera Stream</title>
<style>
  html,body {margin:0;height:100%;background:#000}
  img {width:100%;height:100%;object-fit:contain}
</style>
<img src="/stream" alt="camera stream">
"""

# Генерация MJPEG-потока
def generate():
    while True:
        ret, frame = cap.read()
        if not ret:
            continue
        ok, buffer = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
        if not ok:
            continue
        jpg = buffer.tobytes()
        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg + b"\r\n")

@app.route("/")
def index():
    """Отображает простую страницу с видео"""
    return render_template_string(HTML_PAGE)

@app.route("/stream")
def stream():
    """Отправляет поток MJPEG"""
    return Response(generate(), mimetype="multipart/x-mixed-replace; boundary=frame")


print(f"🚀 Сервер запущен! Открой в браузере: http://localhost:{PORT}")
print(f"или с ПЛК: http://<IP_твоего_ПК>:{PORT}/")
app.run(host="0.0.0.0", port=PORT, threaded=True)
