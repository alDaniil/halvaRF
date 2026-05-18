import cv2                                           # библиотека OpenCV для обработки изображений
import numpy as np                                  # библиотека NumPy для работы с массивами
import os                                            # библиотека для работы с файлами и путями
import time                                          # библиотека для работы со временем

file_path = r"C:/Users/L13 Yoga/Documents/foto1080"  # папка с изображениями

start_img = 1                                        # номер первого изображения
end_img = 999                                        # номер последнего изображения
i = 20                                               # шаг по номерам файлов
t = 300                                              # задержка между сменой кадров в миллисекундах

centers = [                                          # список центров для floodFill
    (700, 245),                                      # 1 - верхнее крупное изделие
    (590, 650),                                      # 2 - левое крупное изделие
    (910, 480),                                      # 3 - правое верхнее изделие
    (850, 750)                                       # 4 - правое среднее изделие
]
bgr_min = np.array([122, 166, 197], dtype=np.uint8)  # начальная нижняя граница BGR
bgr_max = np.array([255, 255, 255], dtype=np.uint8)  # начальная верхняя граница BGR

current_index = 0                                    # индекс текущего изображения в списке
image_files = []                                     # список путей к найденным изображениям
image_numbers = []                                   # список номеров найденных изображений
image = None                                         # текущее загруженное изображение
image_with_centers = None                            # изображение с нарисованными центрами
current_mask_view = None                             # текущая итоговая маска
h, w = 0, 0    

def OpenAndDraw(i):
    img = cv2.imread(file_path, cv2.IMREAD_COLOR)     # читаем изображение в цвете

while (1):
    for current_index in range(1, 999, 20):

        imgMask, img = OpenAndDraw(file_path)    # читаем изображение в цвете


    key = cv2.waitKey(1) & 0xFF                        # читаем нажатую клавишу
    if key == 27:                                      # если нажата клавиша Esc
        break                                          # выходим из цикла

cv2.destroyAllWindows()    
