import cv2
import numpy as np
import time
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

from opcua import Client, ua
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

