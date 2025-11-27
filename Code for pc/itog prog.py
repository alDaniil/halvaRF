import cv2
import numpy as np
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from opcua import Client, ua


# ------------------ НАСТРОЙКИ ------------------

PLC_URL = "opc.tcp://172.16.3.186:4840"   # адрес OPC UA сервера ПЛК
NS_INDEX = 4                              # номер namespace (уточни в UAExpert)
HTTP_PORT = 8000                          # порт веб-сервера
CAM_INDEX = 0                             # номер камеры в OpenCV


# ------------------ ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ ------------------

cap = None                 # объект камеры
last_jpeg = None           # последний JPEG для браузера
last_frame = None          # последний сырой кадр BGR (для анализа)
frame_lock = threading.Lock()

plc_client = None          # объект OPC UA клиента
plc_vars = {}              # словарь узлов TargetVars
plc_lock = threading.Lock()


# ============================================================
#  ПЛК  (OPC UA)
# ============================================================

def connect_plc():
    """
    Подключение к ПЛК и получение узлов TargetVars по реальным NodeId.
    """
    global plc_client, plc_vars

    client = Client("opc.tcp://172.16.3.186:4840")
    client.connect()
    print("✅ ПЛК: подключение по OPC UA выполнено")

    # ТВОИ РЕАЛЬНЫЕ НОДЫ:
    base = "ns=4;s=|var|PLC210 OPC-UA.Application.TargetVars."

    plc_vars = {
        "bNewProduct":   client.get_node(base + "bNewProduct"),
        "bPlcReady":     client.get_node(base + "bPlcReady"),
        "bStartGrab":    client.get_node(base + "bStartGrab"),
        "iPcResult":     client.get_node(base + "iPcResult"),
        "uiPcErrorCode": client.get_node(base + "uiPcErrorCode"),
    }

    # Проверка чтения
    try:
        print("bPlcReady =", plc_vars["bPlcReady"].get_value())
    except Exception as e:
        print("Ошибка чтения bPlcReady:", e)

    plc_client = client
    return client, plc_vars



def safe_read(name):
    """
    Безопасное чтение переменной ПЛК.
    При ошибке пытаемся переподключиться.
    """
    global plc_client

    with plc_lock:
        try:
            return plc_vars[name].get_value()
        except Exception as e:
            print(f"⚠ Ошибка чтения {name}: {e}")
            try:
                plc_client.disconnect()
            except:
                pass
            time.sleep(1.0)
            connect_plc()
            return plc_vars[name].get_value()


def safe_write(name, value, vtype):
    """
    Безопасная запись переменной ПЛК.
    name  – ключ в plc_vars
    value – значение
    vtype – тип ua.VariantType.*
    """
    global plc_client

    with plc_lock:
        try:
            var = ua.Variant(value, vtype)
            plc_vars[name].set_value(var)
        except Exception as e:
            print(f"⚠ Ошибка записи {name}: {e}")
            try:
                plc_client.disconnect()
            except:
                pass
            time.sleep(1.0)
            connect_plc()
            var = ua.Variant(value, vtype)
            plc_vars[name].set_value(var)


def plc_logic_loop():
    """
    Основной цикл логики ПК ↔ ПЛК.
    Ждём bPlcReady/bNewProduct, берём кадр, считаем результат, пишем в ПЛК.
    """
    print("▶ Цикл обмена с ПЛК запущен")

    busy = False  # внутренний флаг: сейчас идёт обработка

    while True:
        try:
            b_ready = safe_read("bPlcReady")
            b_new   = safe_read("bNewProduct")

            # новое изделие и ПЛК говорит "готов"
            if b_ready and b_new and not busy:
                busy = True
                print("📷 Новый объект под камерой, начинаю обработку")

                # ставим флаг для ПЛК, что ПК работает
                safe_write("bStartGrab", True, ua.VariantType.Boolean)
                safe_write("uiPcErrorCode", 0, ua.VariantType.UInt16)

                # берём последний кадр
                with frame_lock:
                    frame = None if last_frame is None else last_frame.copy()

                if frame is None:
                    print("❌ Нет кадра с камеры")
                    safe_write("uiPcErrorCode", 10, ua.VariantType.UInt16)
                    safe_write("iPcResult", 0, ua.VariantType.Int16)
                else:
                    # обработка кадра и вычисление результата
                    result_code = process_and_classify(frame)

                    # пишем результат в ПЛК
                    safe_write("iPcResult", result_code, ua.VariantType.Int16)
                    print(f"✅ Результат анализа отправлен в ПЛК: {result_code}")

                # снимаем флаг "ПК занят"
                safe_write("bStartGrab", False, ua.VariantType.Boolean)
                busy = False

            time.sleep(0.05)

        except Exception as e:
            print("⚠ Ошибка в цикле обмена с ПЛК:", e)
            time.sleep(1.0)


# ============================================================
#  КАМЕРА
# ============================================================

def initial_cam():
    """Первое подключение к камере."""
    global cap
    cap = cv2.VideoCapture(CAM_INDEX)
    if not cap.isOpened():
        print("❌ Камера не обнаружена")
        cap = None
    else:
        print("✅ Камера подключена")


def check_camera():
    """Проверка и автоматическое переподключение камеры."""
    global cap
    while cap is None or not cap.isOpened():
        print("🔄 Пытаюсь подключить камеру...")
        initial_cam()
        if cap is None or not cap.isOpened():
            time.sleep(3)
        else:
            break


def cv_handling(frame_bgr):
    """
    Обработка изображения.
    Сейчас пример: серый + размытие.
    """
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    return blur


def process_and_classify(frame_bgr):
    """
    Логика анализа кадра и выдача кода:
    1 – ОК, 2 – брак, 0 – нет решения.
    Сейчас пример: по средней яркости.
    """
    img = cv_handling(frame_bgr)
    mean_val = float(np.mean(img))

    # простая заглушка:
    # яркий объект – ОК, тёмный – брак
    if mean_val > 100:
        return 1  # ОК
    else:
        return 2  # брак


def camera_loop():
    """
    Поток камеры: постоянно читает кадр, обрабатывает для веба,
    сохраняет последний кадр и JPEG.
    """
    global cap, last_jpeg, last_frame

    JPEG_QUALITY = 80

    check_camera()

    while True:
        if cap is None:
            check_camera()

        ret, frame = cap.read()
        if not ret:
            print("⚠ Не удалось прочитать кадр, пробую снова...")
            time.sleep(0.5)
            continue

        # сохраняем сырой кадр для анализа
        with frame_lock:
            last_frame = frame.copy()

        # для веб — сделаем простую обработку (например, серый)
        processed = cv_handling(frame)

        ok, jpeg = cv2.imencode(".jpg", processed,
                                [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
        if not ok:
            print("⚠ Ошибка кодирования JPEG")
            time.sleep(0.2)
            continue

        with frame_lock:
            last_jpeg = jpeg.tobytes()

        time.sleep(0.1)   # частота обновления картинки в браузере


# ============================================================
#  ВЕБ-СЕРВЕР (отдаёт последнюю картинку)
# ============================================================

def web_loop():
    HTML_PAGE = f"""
    <!doctype html>
    <html>
    <head>
        <meta charset="utf-8">
        <title>Камера</title>
        <style>
            html,body {{margin:0;height:100%;background:#000}}
            img {{width:100%;height:100%;object-fit:contain}}
        </style>
    </head>
    <body>
        <img id="cam" src="/snapshot" alt="camera">
        <script>
            setInterval(function(){{
                var img = document.getElementById("cam");
                img.src = "/snapshot?t=" + Date.now();
            }}, 200);
        </script>
    </body>
    </html>
    """

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            global last_jpeg

            if self.path.startswith("/snapshot"):
                with frame_lock:
                    data = last_jpeg

                if data is None:
                    self.send_error(503, "Кадр ещё не готов")
                    return

                self.send_response(200)
                self.send_header("Content-Type", "image/jpeg")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(200)
                self.send_header("Content-type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(HTML_PAGE.encode("utf-8"))

        def log_message(self, format, *args):
            # отключаем лишние логи в консоль
            return

    server = HTTPServer(("0.0.0.0", HTTP_PORT), Handler)
    print(f"🌐 Веб-сервер: http://localhost:{HTTP_PORT}")
    server.serve_forever()


# ============================================================
#  ЗАПУСК
# ============================================================

def main():
    # подключаемся к ПЛК
    connect_plc()

    # запускаем потоки
    t_web = threading.Thread(target=web_loop, daemon=True)
    t_cam = threading.Thread(target=camera_loop, daemon=True)
    t_plc = threading.Thread(target=plc_logic_loop, daemon=True)

    t_web.start()
    t_cam.start()
    t_plc.start()

    print("▶ Главный цикл запущен. Нажми Ctrl+C для выхода.")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("⏹ Остановка программы...")
        if plc_client is not None:
            plc_client.disconnect()


if __name__ == "__main__":
    main()
