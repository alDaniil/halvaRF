import sys
import os
import cv2
import numpy as np
from opcua import Client
from opcua import ua
from http.server import BaseHTTPRequestHandler, HTTPServer
import time
import threading

# ------------ ПЛК ------------
def initial_plc():
    url = "opc.tcp://172.16.3.186:4840"
    client = Client(url)
    try:
        client.connect()
        print("Подключение к ПЛК прошло успешно")
    except Exception as e:
        try:
            raise RuntimeError(f"Ошибка подключения к ПЛК: {e}")
        except RuntimeError as err:
            print(err)
    return client


# ------------ ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ------------
cap = None                # объект камеры
last_jpeg = None          # последний обработанный JPEG
frame_lock = threading.Lock()  # защита доступа к last_jpeg


# ------------ КАМЕРА ------------
def initial_cam():
    """Первое/обычное подключение к камере."""
    CAM_INDEX = 0
    try:
        cap = cv2.VideoCapture(CAM_INDEX)
        if not cap.isOpened():
            raise RuntimeError("❌ Камера не обнаружена. Проверь подключение.")
        print("Камера подключена")
    except Exception as e:
        print("Ошибка камеры:", e)
        cap = None
    return cap

def check_camera():
    """Проверка и автоматическое переподключение камеры."""
    global cap

    while True:
        if cap is None or not cap.isOpened():
            print("🔄 Пытаюсь подключить камеру...")
            cap = initial_cam()

            if cap is not None and cap.isOpened():
                print("✅ Камера переподключена")
                return cap
            else:
                print("❌ Камера недоступна, пробую снова через 3 сек...")
                time.sleep(3)
                continue

        # камера уже открыта
        return cap


# ------------ ОБРАБОТКА КАДРА (OpenCV) ------------
def cv_handling(frame):
    """
    Здесь выполняется вся обработка изображения.
    Сейчас: перевод в серый цвет.
    Потом можно дописать свою логику.
    """
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return gray


# ------------ ПОТОК КАМЕРЫ ------------
def camera_loop():
    """Отдельный поток: читает, обрабатывает и сохраняет кадры."""
    global cap, last_jpeg

    JPEG_QUALITY = 80

    while True:
        # проверяем/подключаем камеру
        cap = check_camera()

        # читаем кадр
        ret, frame = cap.read()
        if not ret:
            print("Не удалось прочитать кадр, пробую снова...")
            time.sleep(0.5)
            continue

        # обработка кадра в отдельной функции
        processed = cv_handling(frame)

        # кодирование обработанного кадра в JPEG
        ok, jpeg = cv2.imencode(
            ".jpg",
            processed,
            [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY]
        )
        if not ok:
            print("Ошибка кодирования JPEG, пробую снова...")
            time.sleep(0.5)
            continue

        # сохраняем результат для веб-сервера
        with frame_lock:
            last_jpeg = jpeg.tobytes()

        # частота обновления кадров
        time.sleep(0.5)


# ------------ ВЕБ ------------
def web_loop():
    PORT = 8000

    HTML_PAGE = """
    <!doctype html>
    <html>
    <head>
    <meta charset="utf-8">
    <title>Live Camera Snapshot</title>
    <style>
    html,body {margin:0;height:100%;background:#000}
    img {width:100%;height:100%;object-fit:contain}
    </style>
    </head>
    <body>
    <img id="cam" src="/snapshot" alt="camera snapshot">
    <script>
    // раз в 500 мс загружаем новый кадр
    setInterval(function() {
        var img = document.getElementById("cam");
        img.src = "/snapshot?t=" + Date.now();
    }, 500);
    </script>
    </body>
    </html>
    """

    class SnapshotHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            global last_jpeg

            if self.path.startswith("/snapshot"):
                # отдаем последний кадр
                with frame_lock:
                    data = last_jpeg

                if data is None:
                    self.send_error(503, "Кадр ещё не готов")
                    return

                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "image/jpeg")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                except Exception as e:
                    print("Ошибка отправки кадра:", e)

            else:
                # главная страница
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(HTML_PAGE.encode("utf-8"))

    server = HTTPServer(("0.0.0.0", PORT), SnapshotHandler)
    print(f"Веб-сервер запущен: http://localhost:{PORT}")
    server.serve_forever()


# ------------ MAIN ------------
if __name__ == "__main__":
    # если нужно — подключение к ПЛК
    # plc = initial_plc()

    # поток веб-сервера
    web_thread = threading.Thread(target=web_loop, daemon=True)
    web_thread.start()

    # поток камеры
    cam_thread = threading.Thread(target=camera_loop, daemon=True)
    cam_thread.start()

    # твой главный бесконечный цикл управления
    while True:
        # здесь можно:
        #  - общаться с ПЛК
        #  - читать результаты обработки
        #  - реализовать логику состояний и т.п.
        time.sleep(1)
