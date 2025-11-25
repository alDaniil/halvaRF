from opcua import Client
from opcua import ua
import sys
import numpy as np
import cv2 as cv

hsv_min = np.array((0, 54, 5), np.uint8)
hsv_max = np.array((187, 255, 253), np.uint8)

url = "opc.tcp://172.16.3.186:4840"  # Адрес ПЛК
client = Client(url)#
try:
    client.connect()
    print("Подключено к ПЛК")
finally:
    temp_node = client.get_node("ns=4;s=|var|PLC210 OPC-UA.Application.PLC_PRG.temp") #обозначение переменной в питоне (получение узлов node переменных)
    temp = temp_node.get_value() #чтение значения с ПЛК
    print(f"Temeratura: {temp}")

    new_setpoint = ua.DataValue(ua.Variant(73, ua.VariantType.Float)) #создание переменной особого типа для записи в ПЛК
    temp_node.set_value(new_setpoint) # запись в ПЛК

    client.disconnect()
    print("Отключено от ПЛК")