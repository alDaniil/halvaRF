import sys
import os
import cv2
import numpy as np

from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QSlider, QCheckBox, QTabWidget,
    QVBoxLayout, QHBoxLayout, QGridLayout, QGroupBox
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QImage, QPixmap

# Цвета отрисовки (BGR)
color_red   = (0, 0, 255)   # красный — центры/рамки дефектов
color_green = (0, 255, 0)   # зелёный — контуры зон/эллипсов

# Папка с входными изображениями; ожидаются файлы вида 0.png, 1.png, ...
image_folder = r"C:/Users/admin/Documents/foto1080/"
max_images   = 999  # количество кадров по кругу: 0 .. 998

def _clip_rect(img, x, y, w, h):
    """
    Нормализует прямоугольник (x,y,w,h) в границы изображения img.
    Возвращает целочисленные, гарантированно валидные координаты.
    """
    H, W = img.shape[:2]
    x = max(0, min(int(x), W - 1))
    y = max(0, min(int(y), H - 1))
    w = max(1, min(int(w), W - x))
    h = max(1, min(int(h), H - y))
    return x, y, w, h

# =====================
# ПАРАМЕТРЫ/«ТРЕКБАРЫ»
# =====================

class Params:
    """
    Контейнер параметров — аналог набора трекбаров.
    Все поля редактируются слайдерами/чекбоксами в правых вкладках GUI.
    """
    # --- HSV-диапазон основного цвета ---
    LH=0;  LS=0;  LV=51        # нижняя граница (H,S,V)
    UH=220; US=155; UV=255     # верхняя граница (H,S,V)

    # --- Обрезка кадра (crop) ---
    ZoneX=800; ZoneY=61        # левый верхний угол
    ZoneW=1000; ZoneH=1500     # ширина и высота обрезки

    # --- Визуальные флаги ---
    ShowZones=True             # показывать ли кружки зон на кадре
    WhitenOutside=True         # отбеливать ли вне эллипсов

    # --- HSV-диапазон для «чёрных пятен» ---
    LHb=0; LSb=0; LVb=8
    UHB=24; USB=121; UVB=73

# ============================
# ГРАФИЧЕСКИЙ ИНТЕРФЕЙС (PyQt5)
# ============================

class MainUI(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Halva QC — Single Window v3")
        self.params = Params()      # объект с текущими параметрами
        self.img_idx = 0            # индекс текущего файла-кадра

        # ----- ЛЕВАЯ ЧАСТЬ: окно просмотра -----
        self.view = QLabel()                        # место отрисовки кадра
        self.view.setMinimumWidth(480)              # чтобы не сжималось слишком
        self.view.setAlignment(Qt.AlignCenter)      # центрировать картинку

        # ----- ПРАВАЯ ЧАСТЬ: вкладки с параметрами -----
        tabs = QTabWidget()
        tabs.addTab(self.tab_color_detection(), "Color Detection")
        tabs.addTab(self.tab_zones(),            "Detection Zones")
        tabs.addTab(self.tab_black(),            "Black spot setup")

        # ----- Компоновка: лево/право (~1:2 по ширине) -----
        root = QHBoxLayout(self)
        root.addWidget(self.view, 2)    # вес 1 (≈ треть)
        root.addWidget(tabs,  1)        # вес 2 (≈ две трети)

        # ----- Таймер обновления -----
        self.timer = QTimer(self)                   # таймер «кадр за кадром»
        self.timer.timeout.connect(self.update_frame)
        self.timer.start(60)                        # период ~60 мс (≈16 FPS)
    # ---------- Утилиты создания контролов ----------
    def add_slider(self, grid, row, label, minv, maxv, val, on_change):
        """
        Добавляет в сетку grid подпись + горизонтальный слайдер.
        on_change — функция, которой передаём новое значение при движении.
        """
        from PyQt5.QtWidgets import QLabel as QL
        grid.addWidget(QL(label), row, 0)
        s = QSlider(Qt.Horizontal) #Создание текста на трекбаре
        s.setRange(minv, maxv)  #указание его диапазона
        s.setValue(val) #указание начального значения
        s.valueChanged.connect(on_change) #запись нового значения в класс p
        grid.addWidget(s, row, 1) #собственно добаление виджета
        return s

    def add_checkbox(self, grid, row, label, checked, on_change):
        """
        Добавляет чекбокс в сетку grid на всю строку.
        on_change принимает булево значение.
        """
        cb = QCheckBox(label) #создание виджета галочки
        cb.setChecked(checked) #установка первоначального значения TRUE
        cb.toggled.connect(on_change)  #чтение значения нажатого пользователем
        grid.addWidget(cb, row, 0, 1, 2) #собственно добаление виджета
        return cb
    def tab_color_detection(self):
        """Вкладка: HSV для основного цвета + область обрезки + радиусы эллипсов."""
        box = QGroupBox("Main HSV + Crop + Ellipse radii filter")
        grid = QGridLayout(box)

        p = self.params
        # HSV (основной объект)
        self.add_slider(grid,0,"LH",0,255,p.LH, lambda v:setattr(p,"LH",v))
        self.add_slider(grid,1,"LS",0,255,p.LS, lambda v:setattr(p,"LS",v))
        self.add_slider(grid,2,"LV",0,255,p.LV, lambda v:setattr(p,"LV",v))
        self.add_slider(grid,3,"UH",0,255,p.UH, lambda v:setattr(p,"UH",v))
        self.add_slider(grid,4,"US",0,255,p.US, lambda v:setattr(p,"US",v))
        self.add_slider(grid,5,"UV",0,255,p.UV, lambda v:setattr(p,"UV",v))

        # Обрезка (crop)
        self.add_slider(grid,6,"Zone X",0,4000,p.ZoneX, lambda v:setattr(p,"ZoneX",v))
        self.add_slider(grid,7,"Zone Y",0,4000,p.ZoneY, lambda v:setattr(p,"ZoneY",v))
        self.add_slider(grid,8,"Zone W",1,4000,p.ZoneW, lambda v:setattr(p,"ZoneW",v))
        self.add_slider(grid,9,"Zone H",1,4000,p.ZoneH, lambda v:setattr(p,"ZoneH",v))

        w = QWidget(); lay = QVBoxLayout(w); lay.addWidget(box); lay.addStretch(1)
        return w
    def tab_zones(self):
        """Вкладка: координаты центров зон + индивидуальные радиусы + флаги отображения."""
        box = QGroupBox("Zones (centers & individual radii)")
        grid = QGridLayout(box)
        p = self.params

        # Флаги отображения и отбеливания
        self.add_checkbox(grid,12,"Show Zones",p.ShowZones, lambda b:setattr(p,"ShowZones",b))
        self.add_checkbox(grid,13,"Whiten outside ellipses",p.WhitenOutside, lambda b:setattr(p,"WhitenOutside",b))

        w = QWidget(); lay = QVBoxLayout(w); lay.addWidget(box); lay.addStretch(1)
        return w
    def tab_black(self):
        """Вкладка: HSV-диапазон поиска «чёрных пятен»."""
        box = QGroupBox("Black spot HSV")
        grid = QGridLayout(box)
        p = self.params

        self.add_slider(grid,0,"LHBlack",0,255,p.LHb, lambda v:setattr(p,"LHb",v))
        self.add_slider(grid,1,"LSBlack",0,255,p.LSb, lambda v:setattr(p,"LSb",v))
        self.add_slider(grid,2,"LVBlack",0,255,p.LVb, lambda v:setattr(p,"LVb",v))
        self.add_slider(grid,3,"UHBlack",0,255,p.UHB, lambda v:setattr(p,"UHB",v))
        self.add_slider(grid,4,"USBlack",0,255,p.USB, lambda v:setattr(p,"USB",v))
        self.add_slider(grid,5,"UVBlack",0,255,p.UVB, lambda v:setattr(p,"UVB",v))

        w = QWidget(); lay = QVBoxLayout(w); lay.addWidget(box); lay.addStretch(1)
        return w

    # ---------- Главный цикл обработки ----------
    def update_frame(self):
        """
        Считывает очередной кадр, применяет цепочку обработки и обновляет картинку в QLabel.
        """
        # 1) Чтение следующего файла из папки (круговой индекс)
        filename = os.path.join(image_folder, f"{self.img_idx}.png")
        self.img_idx = (self.img_idx + 1) % max_images

        img = cv2.imread(filename)     # исходный BGR-кадр
        if img is None:
            return                     # если файла нет — пропускаем тик

        p = self.params

        # 3) Применяем обрезку (crop) в координатах исходного кадра
        x, y, w, h = p.ZoneX, p.ZoneY, p.ZoneW, p.ZoneH
        x, y, w, h = _clip_rect(img, x, y, w, h)
        img_crop = img[y:y+h, x:x+w]


    def show_image(self, bgr):
        """
        Преобразует BGR->RGB, упаковывает в QImage и показывает в QLabel с масштабированием.
        """
        rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
        h, w = rgb.shape[:2]
        qimg = QImage(rgb.data, w, h, w * 3, QImage.Format_RGB888)
        self.view.setPixmap(QPixmap.fromImage(qimg).scaled(
            self.view.width(), self.view.height(),
            Qt.KeepAspectRatio, Qt.SmoothTransformation
        ))

# ===== Точка входа =====
def main():
    app = QApplication(sys.argv)
    ui = MainUI()
    ui.resize(1400, 720)  # общие габариты окна
    ui.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()