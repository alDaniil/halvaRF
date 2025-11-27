"""
scan_nodes.py
Простой сканер OPC UA для поиска нужных нод на ПЛК210.

- Подключается к OPC UA серверу ПЛК
- Обходит дерево от Objects
- Ищет узлы TargetVars и наши переменные
- Печатает NodeId, BrowseName и DisplayName

Запуск:
    python scan_nodes.py
"""

from opcua import Client
import sys
import time

# ---------- НАСТРОЙКИ ----------

PLC_URL = "opc.tcp://172.16.3.186:4840"   # адрес OPC UA на ПЛК
MAX_DEPTH = 8                             # максимальная глубина обхода

# эти строки будем подсвечивать
HIGHLIGHT_SUBSTRINGS = [
    "TargetVars",
    "bPlcReady",
    "bNewProduct",
    "bStartGrab",
    "iPcResult",
    "uiPcErrorCode",
]


# ---------- ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ----------

def need_highlight(browse_name: str, display_name: str) -> bool:
    """Нужно ли подсветить (интересующая нас нода)."""
    name_lower = (browse_name or "").lower()
    disp_lower = (display_name or "").lower()
    for sub in HIGHLIGHT_SUBSTRINGS:
        if sub.lower() in name_lower or sub.lower() in disp_lower:
            return True
    return False


def print_node(node, level: int):
    """Красивый вывод одной ноды."""
    indent = "  " * level
    try:
        bn = node.get_browse_name().Name
    except Exception:
        bn = "?"
    try:
        dn = node.get_display_name().Text
    except Exception:
        dn = "?"
    nodeid = node.nodeid

    mark = " ***" if need_highlight(bn, dn) else ""
    print(
        f"{indent}- NodeId={nodeid};  BrowseName='{bn}';  DisplayName='{dn}'{mark}"
    )


def walk(node, level: int = 0, max_level: int = 4):
    """Рекурсивный обход дерева OPC UA."""
    if level > max_level:
        return

    print_node(node, level)

    # если нашли TargetVars – покажем ВСЕ его дочерние элементы полностью
    try:
        bn = node.get_browse_name().Name
    except Exception:
        bn = ""

    if "TargetVars" in bn:
        print("  " * level + "  >>> Дочерние переменные TargetVars:")
        for ch in node.get_children():
            print_node(ch, level + 1)
        # дальше глубже под TargetVars обычно не нужно
        return

    # обычный обход
    try:
        children = node.get_children()
    except Exception:
        children = []

    for ch in children:
        walk(ch, level + 1, max_level)


# ---------- ОСНОВНАЯ ЛОГИКА ----------

def main():
    client = Client(PLC_URL)

    try:
        print(f"Пробую подключиться к ПЛК по адресу {PLC_URL} ...")
        client.connect()
        print("✅ Подключение по OPC UA выполнено\n")

        root = client.get_root_node()
        print("Корневой узел:", root)

        # Узел Objects (в нём почти всегда все интересные данные)
        objects = root.get_child(["0:Objects"])
        print("Objects узел:", objects, "\n")

        print("=== НАЧИНАЮ ОБХОД ДЕРЕВА (глубина до", MAX_DEPTH, ") ===\n")
        # обходим всех потомков Objects
        for child in objects.get_children():
            walk(child, level=0, max_level=MAX_DEPTH)

        print("\n=== ОБХОД ЗАВЕРШЁН ===")
        print("Ищи строки с пометкой '***' — это наши TargetVars/переменные.")
        print("NodeId в формате NodeId(ns=..., s='...') скопируешь прямо из консоли.")

    except Exception as e:
        print("❌ Ошибка при работе с OPC UA:", e)
        sys.exit(1)

    finally:
        try:
            client.disconnect()
        except Exception:
            pass
        time.sleep(0.2)


if __name__ == "__main__":
    main()
