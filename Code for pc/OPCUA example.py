from opcua import Client
from opcua import ua
import time



i = -10
qwe = False
client = Client("opc.tcp://172.16.3.186:4840")#

try:
    client.connect()
    xPartAtCamera_node = client.get_node("ns=4;s=|var|PLC210 OPC-UA.Application.PLC_PRG.xPartAtCamera")
    chislo_node = client.get_node("ns=4;s=|var|PLC210 OPC-UA.Application.PLC_PRG.chislo")

    print("Цикл запущен")

    while True:
        # 1. Читаем ОДИН раз за итерацию
        current_status = xPartAtCamera_node.get_value()

        # 2. Логика "переднего фронта" (сработал датчик)
        if current_status and not qwe:
            i += 1
            # Записываем значение
            new_setpoint = ua.DataValue(ua.Variant(float(i), ua.VariantType.Float))
            chislo_node.set_value(new_setpoint)
            print(f"Сработала вспышка! Число: {i}")

        # 3. Запоминаем состояние для следующего шага
        qwe = current_status

        # 4. ОБЯЗАТЕЛЬНО: даем процессору и сети "подышать"
        # 0.01 сек (10 мс) достаточно, чтобы цикл летал и не тормозил ПЛК
        time.sleep(0.01)

except Exception as e:
    print(f"Ошибка: {e}")
finally:
    client.disconnect()