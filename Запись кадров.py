from opcua import Client
from opcua import ua
import sys
import numpy as np
import cv2 

cap = cv2.VideoCapture(1)
cap.set(cv2.CAP_PROP_FPS, 24) # Частота кадров
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920) # Ширина кадров в видеопотоке.
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 1080) # Высота кадров в видеопотоке.
i = 0
while i<1000:
        
    filename = f"C:/Users/L13 Yoga/Documents/foto1080/{i}.png"
    ret, img = cap.read()
    if ret:
        cv2.imwrite(filename, img)
    #cv2.imshow("camera", img)
    
    i+=1