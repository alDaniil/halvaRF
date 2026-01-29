import cv2
import numpy as np
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from datetime import timedelta
import os

from opcua import Client, ua


# ============================================================
#  ЛОГИ (консоль + файл)
# ============================================================

LOG_DIR = r"C:\Users\admin\Documents\halvaRF"
LOG_FILE = os.path.join(LOG_DIR, "halva_log.txt")
os.makedirs(LOG_DIR, exist_ok=True)

START_TIME = time.time()
log_lock = threading.Lock()

def log(message: str, to_plc: bool = True):
    global plc_log_toggle
    dt = time.time() - START_TIME
    td = str(timedelta(seconds=dt))
    if "." in td:
        t_main, t_ms = td.split(".")
        td = f"{t_main}.{t_ms[:3]}"

    line = f"[{td}] {message}"
    print(line)

    with log_lock:
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        except Exception as e:
            print(f"[LOG ERROR] Не удалось записать в файл: {e}")

    # ----  Отправка в ПЛК (только если нужно) ----
    if not to_plc:
        return

    # ВАЖНО: не блокируемся на plc_lock (иначе возможен дедлок с safe_read/safe_write)
    if not plc_lock.acquire(blocking=False):
        return

    try:
        if plc_client is None or not plc_vars:
            return
        if "sLogNew" not in plc_vars or "bLogNew" not in plc_vars:
            return

        # ограничим длину для STRING(255)
        plc_line = line[:250]

        try:
            plc_vars["sLogNew"].set_value(ua.Variant(plc_line, ua.VariantType.String))
            plc_log_toggle = not plc_log_toggle
            plc_vars["bLogNew"].set_value(ua.Variant(plc_log_toggle, ua.VariantType.Boolean))
        except Exception:
            # тут НЕЛЬЗЯ вызывать log(), чтобы не уйти в рекурсию
            return
    finally:
        plc_lock.release()



# ============================================================
#  НАСТРОЙКИ
# ============================================================

PLC_URL = "opc.tcp://172.16.3.186:4840"
HTTP_PORT = 8000
CAM_INDEX = 0

# Реальные ноды (как ты нашёл сканером)
NODE_BASE = "ns=4;s=|var|PLC210 OPC-UA.Application.TargetVars."

RECONNECT_DELAY_SEC = 3.0


# ============================================================
#  ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
# ============================================================

# камера
cap = None
last_jpeg = None
last_frame = None
frame_lock = threading.Lock()

# plc opcua
plc_client = None
plc_vars = {}
plc_lock = threading.Lock()
plc_connected_once = False
plc_log_toggle = False  # для переключения TargetVars.bLogNew

# handshake state
pc_busy = False                  # ПК сейчас обрабатывает изделие
ack_sent = False                 # ACK (bStartGrab=True) уже отправлен для текущего события
current_job_id = 0               # просто для логов


# ============================================================
#  OPC UA (ПЛК)
# ============================================================

def connect_plc() -> bool:
    """
    Одна попытка подключения. Не кидает исключений наружу.
    Возвращает True при успехе.
    """
    global plc_client, plc_vars, plc_connected_once

    try:
        client = Client(PLC_URL)
        client.connect()
    except Exception as e:
        log(f"⚠ ПЛК: нет подключения по OPC UA: {e}")
        plc_client = None
        plc_vars = {}
        return False

    # Сообщение о подключении
    if not plc_connected_once:
        log("✅ ПЛК: подключение по OPC UA выполнено")
        plc_connected_once = True
    else:
        log("🔄 ПЛК: связь восстановлена")

    try:
        vars_map = {
            "bNewProduct":   client.get_node(NODE_BASE + "bNewProduct"),
            "bPlcReady":     client.get_node(NODE_BASE + "bPlcReady"),
            "bStartGrab":    client.get_node(NODE_BASE + "bStartGrab"),
            "iPcResult":     client.get_node(NODE_BASE + "iPcResult"),
            "uiPcErrorCode": client.get_node(NODE_BASE + "uiPcErrorCode"),
            "bLogNew":       client.get_node(NODE_BASE + "bLogNew"),
            "sLogNew":       client.get_node(NODE_BASE + "sLogNew"),
        }
        # Пробное чтение
        _ = vars_map["bPlcReady"].get_value()
    except Exception as e:
        log(f"⚠ ПЛК: подключился, но ноды не читаются: {e}")
        try:
            client.disconnect()
        except Exception:
            pass
        plc_client = None
        plc_vars = {}
        return False

    plc_client = client
    plc_vars = vars_map
    return True


def _default_value(name: str):
    if name in ("bNewProduct", "bPlcReady", "bStartGrab"):
        return False
    if name == "iPcResult":
        return 0
    if name == "uiPcErrorCode":
        return 0
    return None


def safe_read(name: str):
    """
    Безопасное чтение. Не падает. При потере связи — переподключение.
    """
    global plc_client

    with plc_lock:
        if plc_client is None:
            if not connect_plc():
                return _default_value(name)

        try:
            return plc_vars[name].get_value()
        except Exception as e:
            log(f"⚠ ПЛК: ошибка чтения {name}: {e}")
            try:
                plc_client.disconnect()
            except Exception:
                pass
            plc_client = None
            plc_vars.clear()
            time.sleep(RECONNECT_DELAY_SEC)
            return _default_value(name)


def safe_write(name: str, value, vtype):
    """
    Безопасная запись. Не падает. При потере связи — переподключение.
    """
    global plc_client

    with plc_lock:
        if plc_client is None:
            if not connect_plc():
                log(f"⚠ ПЛК: нет связи, не могу записать {name}")
                time.sleep(RECONNECT_DELAY_SEC)
                return False

        try:
            plc_vars[name].set_value(ua.Variant(value, vtype))
            return True
        except Exception as e:
            log(f"⚠ ПЛК: ошибка записи {name}: {e}")
            try:
                plc_client.disconnect()
            except Exception:
                pass
            plc_client = None
            plc_vars.clear()
            time.sleep(RECONNECT_DELAY_SEC)
            return False


# ============================================================
#  КАМЕРА
# ============================================================

def initial_cam():
    global cap
    cap = cv2.VideoCapture(CAM_INDEX)
    if not cap.isOpened():
        log("❌ Камера не обнаружена")
        cap = None
    else:
        log(" Камера подключена")


def check_camera():
    global cap
    while cap is None or not cap.isOpened():
        log("🔄 Камера недоступна, пытаюсь подключить...")
        initial_cam()
        if cap is None or not cap.isOpened():
            time.sleep(3)
        else:
            break


def cv_handling(frame_bgr):
    # Пример обработки
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    return blur


def process_and_classify(frame_bgr) -> int:
    """
    Вернуть:
      1 = ОК
      2 = БРАК
      0 = нет решения/ошибка
    """
    img = cv_handling(frame_bgr)
    mean_val = float(np.mean(img))

    # Заглушка
    return 1 if mean_val > 100 else 2


def camera_loop():
    global cap, last_jpeg, last_frame

    JPEG_QUALITY = 80
    check_camera()

    while True:
        if cap is None or not cap.isOpened():
            log("🔄 Камера недоступна, переподключаю...")
            check_camera()
            time.sleep(1)  # важно: не грузить CPU
            continue

        ret, frame = cap.read()
        if not ret or frame is None:
            log("⚠ Камера: не удалось прочитать кадр — переподключаю")
            try:
                cap.release()
            except Exception:
                pass
            cap = None
            time.sleep(1)
            continue

        with frame_lock:
            last_frame = frame.copy()

        processed = cv_handling(frame)
        ok, jpeg = cv2.imencode(".jpg", processed, [int(cv2.IMWRITE_JPEG_QUALITY), JPEG_QUALITY])
        if ok:
            with frame_lock:
                last_jpeg = jpeg.tobytes()

        time.sleep(0.1)


# ============================================================
#  ВЕБ (просмотр последнего кадра)
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
    log(f"🌐 Веб-сервер: http://localhost:{HTTP_PORT}")
    server.serve_forever()


# ============================================================
#  HANDSHAKE: основной цикл ПК ↔ ПЛК
# ============================================================

def plc_handshake_loop():
    """
    Handshake без пропусков:
    - ждём bPlcReady && bNewProduct
    - сразу ACK: bStartGrab=True
    - делаем снимок и анализ
    - пишем iPcResult
    - сбрасываем bStartGrab=False (готово)
    """
    global pc_busy, ack_sent, current_job_id

    log("▶ Handshake цикл ПК↔ПЛК запущен")

    while True:
        try:
            b_ready = bool(safe_read("bPlcReady"))
            b_new = bool(safe_read("bNewProduct"))

            # Если ПЛК не готов или нет нового продукта — сбрасываем локальные флаги ожидания
            # (это помогает корректно пережить уход изделия)
            if not b_ready or not b_new:
                if not pc_busy:
                    ack_sent = False
                time.sleep(0.02)
                continue

            # Событие: изделие готово и новое
            if b_ready and b_new and (not pc_busy):
                pc_busy = True
                current_job_id += 1
                job = current_job_id
                log(f"📷 JOB#{job}: получен запрос от ПЛК (bNewProduct=1, bPlcReady=1)")

                # 1) ACK сразу
                if safe_write("bStartGrab", True, ua.VariantType.Boolean):
                    ack_sent = True
                    log(f"📌 JOB#{job}: ACK отправлен (bStartGrab=1)")

                # 2) берём кадр
                with frame_lock:
                    frame = None if last_frame is None else last_frame.copy()

                if frame is None:
                    log(f"❌ JOB#{job}: нет кадра для анализа")
                    safe_write("uiPcErrorCode", 10, ua.VariantType.UInt16)
                    safe_write("iPcResult", 0, ua.VariantType.Int16)
                else:
                    # 3) анализ
                    result_code = process_and_classify(frame)

                    # 4) запись результата
                    safe_write("uiPcErrorCode", 0, ua.VariantType.UInt16)
                    safe_write("iPcResult", int(result_code), ua.VariantType.Int16)
                    log(f"✅ JOB#{job}: результат отправлен в ПЛК iPcResult={result_code}")

                # 5) завершение: сброс ACK
                safe_write("bStartGrab", False, ua.VariantType.Boolean)
                log(f"🏁 JOB#{job}: завершено (bStartGrab=0)")

                pc_busy = False
                time.sleep(0.02)
                continue

            time.sleep(0.02)

        except Exception as e:
            log(f"⚠ Ошибка в handshake цикле: {e}")
            time.sleep(1.0)


# ============================================================
#  ЗАПУСК
# ============================================================

def main():
    # попытка подключения к ПЛК (если не получится — дальше всё равно стартуем)
    connect_plc()

    t_web = threading.Thread(target=web_loop, daemon=True)
    t_cam = threading.Thread(target=camera_loop, daemon=True)
    t_plc = threading.Thread(target=plc_handshake_loop, daemon=True)

    t_web.start()
    t_cam.start()
    t_plc.start()

    log("▶ Программа запущена. Ctrl+C для выхода.")

    try:
        while True:
            time.sleep(1)
            # редкий “пульс” в лог
            log(f"STATUS: plcReady={safe_read('bPlcReady')}")
    except KeyboardInterrupt:
        log("⏹ Остановка программы...")
        with plc_lock:
            if plc_client is not None:
                try:
                    plc_client.disconnect()
                except Exception:
                    pass


if __name__ == "__main__":
    main()
