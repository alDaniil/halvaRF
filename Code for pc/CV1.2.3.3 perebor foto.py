"""
Описание:
    Программа последовательно перебирает изображения из папки, выполняет цветовую
    фильтрацию в HSV, ищет эллипсы в заданных зонах и определяет чёрные пятна.
    Настройки диапазонов и зон задаются с помощью трекбаров (ползунков OpenCV).
    Добавлен трекбар 'Show Zones' для отображения зелёных кругов-зон.
"""

import cv2
import numpy as np
import os

# === Глобальные константы ===
color_red = (0, 0, 255)     # Красный цвет для отметки ошибок
color_green = (0, 255, 0)   # Зелёный цвет для выделения зон
image_folder = "C:/Users/L13 Yoga/Documents/foto1080/"  # Путь к изображениям
max_images = 999  # Максимальное количество изображений для перебора


# === Вспомогательная функция: ничего не делает (нужна для трекбаров) ===
def nothing(x=None):
    pass


# === Создание всех окон и трекбаров ===
def create_trackbars() -> None:
    """Создаёт все окна с трекбарами для настройки HSV диапазонов, зон и радиусов."""

    # Главное окно — настройка цветового диапазона
    cv2.namedWindow('Color Detection', cv2.WINDOW_NORMAL)
    cv2.resizeWindow('Color Detection', 400, 300)

    # Окно зон обнаружения
    cv2.namedWindow('Detection Zones', cv2.WINDOW_NORMAL)
    cv2.resizeWindow('Detection Zones', 400, 500)

    # Окно для настройки диапазона чёрных пятен
    cv2.namedWindow('Black spot setup', cv2.WINDOW_NORMAL)
    cv2.resizeWindow('Black spot setup', 400, 200)

    # HSV диапазон для основного цвета
    for name, val in [('LH', 0), ('LS', 0), ('LV', 51),
                      ('UH', 220), ('US', 155), ('UV', 255)]:
        cv2.createTrackbar(name, 'Color Detection', val, 255, nothing)

    # Зона обрезки изображения
    for name, val in [('Zone X', 800), ('Zone Y', 61),
                      ('Zone Width', 1000), ('Zone Height', 1500)]:
        cv2.createTrackbar(name, 'Color Detection', val, 1500, nothing)

    # Радиусы окружностей
    cv2.createTrackbar('Min Radius', 'Color Detection', 110, 300, nothing)
    cv2.createTrackbar('Max Radius', 'Color Detection', 160, 300, nothing)

    # Зоны детекции и радиус для каждой
    zone_params = [
        ('X1', 264), ('Y1', 318),
        ('X2', 528), ('Y2', 135),
        ('X3', 352), ('Y3', 562),
        ('X4', 670), ('Y4', 420),
        ('Zone Radius', 53)
    ]
    for name, val in zone_params:
        cv2.createTrackbar(name, 'Detection Zones', val,
                           1500 if 'Radius' not in name else 500, nothing)

    # Переключатель отображения зон
    cv2.createTrackbar('Show Zones', 'Detection Zones', 1, 1, nothing)

    # HSV диапазон для поиска чёрных пятен
    for name, val in [('LHBlack', 0), ('LSBlack', 0), ('LVBlack', 8),
                      ('UHBlack', 24), ('USBlack', 121), ('UVBlack', 73)]:
        cv2.createTrackbar(name, 'Black spot setup', val, 255, nothing)


# === Получение значений со всех трекбаров ===
def get_trackbar_values() -> dict:
    """Считывает текущие значения всех трекбаров и возвращает словарь параметров."""
    vals = {}

    # HSV диапазон
    for name in ['LH', 'LS', 'LV', 'UH', 'US', 'UV']:
        vals[name] = cv2.getTrackbarPos(name, 'Color Detection')

    # Зона обрезки
    for name in ['Zone X', 'Zone Y', 'Zone Width', 'Zone Height']:
        vals[name] = cv2.getTrackbarPos(name, 'Color Detection')

    # Радиусы
    vals['Min Radius'] = cv2.getTrackbarPos('Min Radius', 'Color Detection')
    vals['Max Radius'] = cv2.getTrackbarPos('Max Radius', 'Color Detection')

    # Зоны и радиус
    for name in ['X1', 'Y1', 'X2', 'Y2', 'X3', 'Y3', 'X4', 'Y4', 'Zone Radius']:
        vals[name] = cv2.getTrackbarPos(name, 'Detection Zones')

    # Переключатель отображения зон
    vals['Show Zones'] = cv2.getTrackbarPos('Show Zones', 'Detection Zones')

    # Диапазон HSV для чёрных пятен
    for name in ['LHBlack', 'LSBlack', 'LVBlack', 'UHBlack', 'USBlack', 'UVBlack']:
        vals[name] = cv2.getTrackbarPos(name, 'Black spot setup')

    return vals


# === Поиск и отрисовка эллипсов в заданных зонах ===
def find_and_draw_largest_ellipses(
    img: np.ndarray,
    img_clean: np.ndarray,
    mask: np.ndarray,
    zones: list[tuple[int, int]],
    zone_radius: int,
    min_r: int = 110,
    max_r: int = 160,
    max_circles: int = 3
) -> tuple[np.ndarray, list[tuple[int, int, int, int, int]]]:
    """
    Находит эллипсы в заданных зонах по маске и рисует центры на изображении.
    Возвращает обновлённое изображение и список найденных эллипсов.
    """

    ellipses = []
    # Поиск контуров на бинарной маске
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    for cnt in contours:
        if len(cnt) < 5:
            continue  # Недостаточно точек для аппроксимации эллипса

        (cx, cy), axes, angle = cv2.fitEllipse(cnt)  # Аппроксимация контуров эллипсом

        # Проверка попадания центра в одну из зон
        for zx, zy in zones:
            if (cx - zx) ** 2 + (cy - zy) ** 2 <= zone_radius ** 2:
                ellipses.append((int(cx), int(cy), int(axes[0] * 0.65), int(axes[1] * 0.7), int(angle)))
                break

    # Сортировка по размеру и выбор максимальных N эллипсов
    ellipses = sorted(ellipses, key=lambda c: c[3], reverse=True)[:max_circles]

    # Отрисовка центров эллипсов
    for (cx, cy, axes1, axes2, angle) in ellipses:
        cv2.circle(img_clean, (cx, cy), 2, color_green, -1)
        cv2.putText(img_clean, "cen", (cx - 25, cy - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color_green, 2)

    return img_clean, ellipses


# === Белая заливка области вне найденных эллипсов ===
def white_mask_outside_ellipses(img: np.ndarray, ellipses: list[tuple[int, int, int, int, int]]) -> np.ndarray:
    """
    Оставляет внутри эллипсов исходное изображение, остальное заменяет белым цветом.
    """
    mask = np.full(img.shape[:2], 255, dtype=np.uint8)
    for (cx, cy, ax, ay, angle) in ellipses:
        cv2.ellipse(mask, (cx, cy), (ax, ay), angle, 0, 360, 0, -1)

    mask_inv = cv2.bitwise_not(mask)
    result_ellipses = cv2.bitwise_and(img, img, mask=mask_inv)

    white_background = np.full_like(img, 255)
    result = np.where(result_ellipses == 0, white_background, result_ellipses)
    return result


# === Обнаружение чёрных пятен ===
def detect_black_spot(img: np.ndarray, lower_black: np.ndarray, upper_black: np.ndarray) -> np.ndarray:
    """
    Ищет чёрные пятна на изображении в заданном HSV диапазоне.
    Отмечает прямоугольники вокруг найденных пятен.
    """
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, lower_black, upper_black)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > 10:  # Фильтр по минимальной площади
            x, y, w, h = cv2.boundingRect(cnt)
            cv2.rectangle(img, (x, y), (x + w, y + h), color_red, 2)
            cv2.putText(img, f"{int(area)}", (x, y - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color_red, 1)
    return img


# === Визуализация диапазона HSV ===
def draw_hsv_display(lh, ls, lv, uh, us, uv, title: str, label: str) -> None:
    """Отображает плавный градиент HSV диапазона для наглядности."""
    color_display = np.full((100, 400, 3), 255, dtype=np.uint8)
    for x_grad in range(400):
        ratio = x_grad / 399.0
        hsv_color = np.array([
            int(lh + ratio * (uh - lh)),
            int(ls + ratio * (us - ls)),
            int(lv + ratio * (uv - lv))
        ], dtype=np.uint8)
        bgr_color = cv2.cvtColor(np.uint8([[hsv_color]]), cv2.COLOR_HSV2BGR)[0][0]
        color_display[:, x_grad] = bgr_color

    cv2.putText(color_display, "MIN", (20, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
    cv2.putText(color_display, "MAX", (330, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
    cv2.putText(color_display, label, (50, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 1)
    cv2.imshow(title, color_display)


# === Главный цикл программы ===
def main():
    """Основной цикл обработки изображений."""
    create_trackbars()
    i = 0

    while True:
        vals = get_trackbar_values()

        # === Извлечение диапазонов HSV ===
        lh, ls, lv = vals['LH'], vals['LS'], vals['LV']
        uh, us, uv = vals['UH'], vals['US'], vals['UV']

        lhBlack, lsBlack, lvBlack = vals['LHBlack'], vals['LSBlack'], vals['LVBlack']
        uhBlack, usBlack, uvBlack = vals['UHBlack'], vals['USBlack'], vals['UVBlack']

        # === Зона обрезки и радиусы ===
        x, y, w, h = vals['Zone X'], vals['Zone Y'], vals['Zone Width'], vals['Zone Height']
        min_r, max_r = vals['Min Radius'], vals['Max Radius']
        if min_r > max_r:
            min_r = max_r

        # === Зоны детекции ===
        zones = [(vals['X1'], vals['Y1']), (vals['X2'], vals['Y2']),
                 (vals['X3'], vals['Y3']), (vals['X4'], vals['Y4'])]
        zone_r = vals['Zone Radius']
        show_zones = vals['Show Zones']

        # === Диапазоны HSV в формате numpy ===
        hsv_min = np.array((lh, ls, lv), np.uint8)
        hsv_max = np.array((uh, us, uv), np.uint8)
        hsv_min_Black = np.array((lhBlack, lsBlack, lvBlack), np.uint8)
        hsv_max_Black = np.array((uhBlack, usBlack, uvBlack), np.uint8)

        # === Загрузка изображения ===
        filename = os.path.join(image_folder, f"{i}.png")
        i = (i + 1) % max_images
        img = cv2.imread(filename)
        if img is None:
            print(f"Фото {filename} отсутствует.")
            break

        # === Основная обработка ===
        img = img[y:y + h, x:x + w]
        hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
        mask = cv2.inRange(hsv, hsv_min, hsv_max)
        img_masked = cv2.bitwise_and(img, img, mask=mask)

        # === Отрисовка зон (если включено) ===
        if show_zones:
            for zx, zy in zones:
                cv2.circle(img_masked, (zx, zy), zone_r, color_green, 2)
                cv2.circle(img_masked, (zx, zy), 3, color_green, -1)

        # Поиск эллипсов и чёрных пятен
        figure_img, figure = find_and_draw_largest_ellipses(img_masked, img.copy(), mask, zones, zone_r, min_r, max_r)
        white_img = white_mask_outside_ellipses(figure_img, figure)
        img_result = detect_black_spot(white_img, hsv_min_Black, hsv_max_Black)

        # === Отображение зон в итоговом изображении (если включено) ===
        if show_zones:
            for zx, zy in zones:
                cv2.circle(img_result, (zx, zy), zone_r, color_green, 2)
                cv2.circle(img_result, (zx, zy), 3, color_green, -1)

        cv2.imshow("Detected Circles", img_result)

        # Визуализация диапазонов
        draw_hsv_display(lh, ls, lv, uh, us, uv, "Color Detection", "Main Color Detection Range")
        draw_hsv_display(lhBlack, lsBlack, lvBlack, uhBlack, usBlack, uvBlack, "Black spot setup", "Black Spot HSV Range")

        # ESC — выход
        if cv2.waitKey(10) & 0xFF == 27:
            break

    cv2.destroyAllWindows()


# === Точка входа ===
if __name__ == "__main__":
    main()
