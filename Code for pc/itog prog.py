import cv2
import numpy as np
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from opcua import Client, ua


# ------------------ НАСТРОЙКИ ------------------

PLC_URL = "opc.tcp://172.16.3.186:4840"   # адрес OPC UA сервера ПЛК
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
plc_connected_once = False # флаг: было ли успешное подключение хоть раз



# ============================================================
#  ПЛК  (OPC UA)
# ============================================================

def connect_plc():
    """
    ОДНОКРАТНАЯ попытка подключиться к ПЛК и получить узлы TargetVars.
    Возвращает True/False.
    """
    global plc_client, plc_vars, plc_connected_once

    try:
        client = Client(PLC_URL)
        client.connect()
    except Exception:
        # если не подключились — ничего не выводим
        plc_client = None
        plc_vars = {}
        return False

    # если подключились — выводим сообщение только ПЕРВЫЙ РАЗ
    if not plc_connected_once:
        print("✅ ПЛК: подключение по OPC UA выполнено")
        plc_connected_once = True

    base = "ns=4;s=|var|PLC210 OPC-UA.Application.TargetVars."

    try:
        vars_map = {
            "bNewProduct":   client.get_node(base + "bNewProduct"),
            "bPlcReady":     client.get_node(base + "bPlcReady"),
            "bStartGrab":    client.get_node(base + "bStartGrab"),
            "iPcResult":     client.get_node(base + "iPcResult"),
            "uiPcErrorCode": client.get_node(base + "uiPcErrorCode"),
        }

        # пробное чтение
        _ = vars_map["bPlcReady"].get_value()

    except Exception:
        try:
            client.disconnect()
        except:
            pass
        plc_client = None
        plc_vars = {}
        return False

    # успех
    plc_client = client
    plc_vars = vars_map
    return True


def _default_value(name: str):
    """
    Значение по умолчанию, когда ПЛК недоступен.
    """
    if name in ("bNewProduct", "bPlcReady", "bStartGrab"):
        return False
    if name == "iPcResult":
        return 0
    if name == "uiPcErrorCode":
        return 0
    return None


def safe_read(name):
    """
    Безопасное чтение переменной ПЛК.
    Никогда не бросает исключений.
    При отсутствии связи возвращает значение по умолчанию и
    каждые 3 сек пытается переподключиться.
    """
    global plc_client

    with plc_lock:
        # если ещё не подключались или соединение уже закрыто
        if plc_client is None:
            ok = connect_plc()
            if not ok:
                # нет связи — вернём дефолт
                return _default_value(name)

        try:
            return plc_vars[name].get_value()
        except Exception as e:
            print(f"⚠ Ошибка чтения {name}: {e}")
            # считаем, что связь потеряна
            try:
                plc_client.disconnect()
            except Exception:
                pass
            plc_client = None
            plc_vars.clear()
            # небольшая пауза перед следующей попыткой
            time.sleep(3.0)
            return _default_value(name)


def safe_write(name, value, vtype):
    """
    Безопасная запись переменной ПЛК.
    Если связи нет — просто пишет предупреждение, но программу не роняет.
    """
    global plc_client

    with plc_lock:
        if plc_client is None:
            # пробуем переподключиться
            ok = connect_plc()
            if not ok:
                print(f"⚠ Нет связи с ПЛК, не могу записать {name}")
                time.sleep(3.0)
                return

        try:
            var = ua.Variant(value, vtype)
            plc_vars[name].set_value(var)
        except Exception as e:
            print(f"⚠ Ошибка записи {name}: {e}")
            try:
                plc_client.disconnect()
            except Exception:
                pass
            plc_client = None
            plc_vars.clear()
            time.sleep(3.0)


def plc_logic_loop():
    """
    Основной цикл логики ПК ↔ ПЛК.
    Ждём bPlcReady/bNewProduct, берём кадр, считаем результат, пишем в ПЛК.
    Даже при потере связи не вылетает — safe_read/safe_write всё глотают.
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
                    safe_write("iPcResult", result_code, ua.VariantType.Int16)
                    print(f"✅ Результат анализа отправлен в ПЛК: {result_code}")

                safe_write("bStartGrab", False, ua.VariantType.Boolean)
                busy = False

            time.sleep(0.05)

        except Exception as e:
            # сюда вообще не должны попадать, но на всякий случай
            print("⚠ Неожиданная ошибка в цикле обмена с ПЛК:", e)
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
    """Обработка изображения (пример: серый + размытие)."""
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

    if mean_val > 100:
        return 1  # ОК
    else:
        return 2  # брак


def camera_loop():
    """
    Поток камеры: читает кадр, обрабатывает для веба,
    сохраняет последний кадр и JPEG.
    """
    global cap, last_jpeg, last_frame

    JPEG_QUALITY = 80

    check_camera()

    while True:
        # Если камера отсутствует — пробуем переподключить
        if cap is None or not cap.isOpened():
            print("🔄 Камера недоступна, переподключаю...")
            check_camera()
            time.sleep(1)
            continue

        # Пытаемся прочитать кадр
        ret, frame = cap.read()

        if not ret or frame is None:
            print("⚠ Не удалось прочитать кадр — камера возможно потеряна")
            # Считаем камеру отключённой
            try:
                cap.release()
            except Exception:
                pass
            cap = None
            # Идём переподключаться
            time.sleep(1)
            continue

        # Сохраняем сырой кадр для анализа
        with frame_lock:
            last_frame = frame.copy()

        # JPEG нужен только для веба, можно сделать обработку
        processed = cv_handling(frame)

        ok, jpeg = cv2.imencode(".jpg", processed,
                                [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])

        if not ok:
            print("⚠ Ошибка JPEG-кодирования — проверяю камеру")
            # Такое бывает при потерянных фреймах — но камера скорее всего жива
            time.sleep(0.2)
            continue

        with frame_lock:
            last_jpeg = jpeg.tobytes()

        # Скорость обновления
        time.sleep(0.1)


# ============================================================
#  ВЕБ-СЕРВЕР
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
            return

    server = HTTPServer(("0.0.0.0", HTTP_PORT), Handler)
    print(f"🌐 Веб-сервер: http://localhost:{HTTP_PORT}")
    server.serve_forever()


# ======================================= =====================
#  ЗАПУСК
# ============================================================

def main():
    # первую попытку подключения к ПЛК делаем сразу,
    # но если не получится – программа всё равно продолжит жить
    connect_plc()

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
            # для контроля можем периодически печатать состояние флага
            print("bPlcReady =", safe_read("bPlcReady"))
    except KeyboardInterrupt:
        print("⏹ Остановка программы...")
        with plc_lock:
            if plc_client is not None:
                try:
                    plc_client.disconnect()
                except Exception:
                    pass


if __name__ == "__main__":
    main()
