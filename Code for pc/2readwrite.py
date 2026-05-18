import cv2
import numpy as np
import os
import time


# ============================================================
# ПАПКА С ИЗОБРАЖЕНИЯМИ
# ============================================================

folder_path = r"C:/Users/L13 Yoga/Pictures/fotoLed1080"

start_img = 618        # первый номер изображения 618
end_img = 764          # последний номер изображения 764
i = 1                  # шаг по номерам файлов
t = 1000               # задержка между кадрами, мс


# ============================================================
# РАБОЧАЯ ОБЛАСТЬ ПО ЧЕТЫРЕМ УГЛАМ
#
# Порядок точек:
# 1 — левый верхний угол
# 2 — правый верхний угол
# 3 — правый нижний угол
# 4 — левый нижний угол
# ============================================================

work_area_points = np.array([
    [770, 418],     # точка 1: P1 X horizontal, P1 Y vertical
    [1305, 492],    # точка 2: P2 X horizontal, P2 Y vertical
    [1230, 900],    # точка 3: P3 X horizontal, P3 Y vertical
    [405, 705],     # точка 4: P4 X horizontal, P4 Y vertical
], dtype=np.int32)


# ============================================================
# НАСТРОЙКИ ПОИСКА ПЯТЕН
# ============================================================

dark_gray_thresh = 54        # порог темного пятна по серому изображению
min_spot_area = 20           # минимальная площадь пятна
max_spot_area = 5000         # максимальная площадь пятна

remove_yellow = True         # True — вычитать желтый коррекс из рабочей области

yellow_h_min = 15
yellow_h_max = 45
yellow_s_min = 70
yellow_s_max = 255
yellow_v_min = 70
yellow_v_max = 255


# ============================================================
# ГЛОБАЛЬНЫЕ ПЕРЕМЕННЫЕ
# ============================================================

current_index = 0
image_files = []
image_numbers = []

image = None
image_with_area = None
current_mask_view = None
spot_mask_view = None
result_view = None

h, w = 0, 0

last_reported_image_number = None
trackbars_created = False
need_rebuild = False


# ============================================================
# ПОИСК ФАЙЛОВ
# ============================================================

for num in range(start_img, end_img + 1, i):
    file_path = os.path.join(folder_path, f"{num}.png")

    if os.path.exists(file_path):
        image_files.append(file_path)
        image_numbers.append(num)

if not image_files:
    print("Ошибка: не найдено ни одного изображения.")
    exit()


# ============================================================
# ПОЛУЧЕНИЕ ИМЕНИ ТЕКУЩЕГО ФАЙЛА
# ============================================================

def get_current_image_name():
    if not image_files:
        return "No image"

    return os.path.basename(image_files[current_index])


# ============================================================
# ТРЕКБАРЫ
# ============================================================

def on_trackbar_change(value):
    global need_rebuild
    need_rebuild = True


def create_trackbars():
    global trackbars_created

    if trackbars_created:
        return

    cv2.namedWindow("5 Work area setup", cv2.WINDOW_NORMAL)

    max_x = max(w - 1, 1)
    max_y = max(h - 1, 1)

    cv2.createTrackbar(
        "P1 X horizontal",
        "5 Work area setup",
        int(work_area_points[0][0]),
        max_x,
        on_trackbar_change
    )

    cv2.createTrackbar(
        "P1 Y vertical",
        "5 Work area setup",
        int(work_area_points[0][1]),
        max_y,
        on_trackbar_change
    )

    cv2.createTrackbar(
        "P2 X horizontal",
        "5 Work area setup",
        int(work_area_points[1][0]),
        max_x,
        on_trackbar_change
    )

    cv2.createTrackbar(
        "P2 Y vertical",
        "5 Work area setup",
        int(work_area_points[1][1]),
        max_y,
        on_trackbar_change
    )

    cv2.createTrackbar(
        "P3 X horizontal",
        "5 Work area setup",
        int(work_area_points[2][0]),
        max_x,
        on_trackbar_change
    )

    cv2.createTrackbar(
        "P3 Y vertical",
        "5 Work area setup",
        int(work_area_points[2][1]),
        max_y,
        on_trackbar_change
    )

    cv2.createTrackbar(
        "P4 X horizontal",
        "5 Work area setup",
        int(work_area_points[3][0]),
        max_x,
        on_trackbar_change
    )

    cv2.createTrackbar(
        "P4 Y vertical",
        "5 Work area setup",
        int(work_area_points[3][1]),
        max_y,
        on_trackbar_change
    )

    cv2.createTrackbar(
        "Dark gray threshold",
        "5 Work area setup",
        int(dark_gray_thresh),
        255,
        on_trackbar_change
    )

    trackbars_created = True


def update_settings_from_trackbars():
    global work_area_points, dark_gray_thresh

    if not trackbars_created:
        return

    p1x = cv2.getTrackbarPos("P1 X horizontal", "5 Work area setup")
    p1y = cv2.getTrackbarPos("P1 Y vertical", "5 Work area setup")

    p2x = cv2.getTrackbarPos("P2 X horizontal", "5 Work area setup")
    p2y = cv2.getTrackbarPos("P2 Y vertical", "5 Work area setup")

    p3x = cv2.getTrackbarPos("P3 X horizontal", "5 Work area setup")
    p3y = cv2.getTrackbarPos("P3 Y vertical", "5 Work area setup")

    p4x = cv2.getTrackbarPos("P4 X horizontal", "5 Work area setup")
    p4y = cv2.getTrackbarPos("P4 Y vertical", "5 Work area setup")

    dark_gray_thresh = cv2.getTrackbarPos(
        "Dark gray threshold",
        "5 Work area setup"
    )

    work_area_points = np.array([
        [p1x, p1y],
        [p2x, p2y],
        [p3x, p3y],
        [p4x, p4y],
    ], dtype=np.int32)


def print_current_settings():
    print("\nТекущие координаты work_area_points:")
    print("work_area_points = np.array([")

    for idx, point in enumerate(work_area_points, start=1):
        x, y = point
        print(f"    [{x}, {y}],    # точка {idx}")

    print("], dtype=np.int32)")

    print(f"\ndark_gray_thresh = {dark_gray_thresh}")
    print(f"remove_yellow = {remove_yellow}")
    print(f"Текущее изображение: {get_current_image_name()}")


# ============================================================
# ОТРИСОВКА ЧЕТЫРЕХУГОЛЬНОЙ ОБЛАСТИ
# ============================================================

def draw_work_area(img):
    out = img.copy()

    pts = work_area_points.reshape((-1, 1, 2))

    cv2.polylines(
        out,
        [pts],
        isClosed=True,
        color=(0, 0, 255),
        thickness=3
    )

    for idx, point in enumerate(work_area_points, start=1):
        x, y = point

        cv2.circle(out, (x, y), 8, (255, 0, 0), -1)

        cv2.putText(
            out,
            f"P{idx}",
            (x + 10, y - 10),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.8,
            (0, 0, 255),
            2,
            cv2.LINE_AA
        )

    # Вместо dark_gray_thresh теперь показываем имя изображения
    cv2.putText(
        out,
        f"Image: {get_current_image_name()}",
        (30, 50),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (0, 0, 255),
        2,
        cv2.LINE_AA
    )

    return out


# ============================================================
# СОЗДАНИЕ МАСКИ ПО ЧЕТЫРЕМ ТОЧКАМ
# ============================================================

def make_work_area_mask():
    mask = np.zeros((h, w), dtype=np.uint8)

    pts = work_area_points.reshape((-1, 1, 2))

    cv2.fillPoly(mask, [pts], 255)

    return mask


# ============================================================
# УДАЛЕНИЕ ЖЕЛТОГО КОРРЕКСА ИЗ МАСКИ
# ============================================================

def remove_yellow_tray_from_mask(img, mask):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

    lower_yellow = np.array(
        [yellow_h_min, yellow_s_min, yellow_v_min],
        dtype=np.uint8
    )

    upper_yellow = np.array(
        [yellow_h_max, yellow_s_max, yellow_v_max],
        dtype=np.uint8
    )

    yellow_mask = cv2.inRange(hsv, lower_yellow, upper_yellow)

    result = mask.copy()
    result[yellow_mask > 0] = 0

    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    result = cv2.morphologyEx(
        result,
        cv2.MORPH_CLOSE,
        kernel_close,
        iterations=1
    )

    return result


# ============================================================
# ПОИСК ЧЕРНЫХ И СЕРЫХ ПЯТЕН ВНУТРИ ЧЕТЫРЕХУГОЛЬНОЙ ОБЛАСТИ
# ============================================================

def detect_dark_and_gray_spots():
    global spot_mask_view, result_view, last_reported_image_number

    if image is None or current_mask_view is None:
        return

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    masked_gray = cv2.bitwise_and(gray, gray, mask=current_mask_view)

    spot_mask = np.zeros_like(gray, dtype=np.uint8)

    # Темные пиксели только внутри рабочей области
    spot_mask[(current_mask_view > 0) & (masked_gray < dark_gray_thresh)] = 255

    # Морфология для удаления мелкого шума
    kernel_open = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
    kernel_close = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))

    spot_mask = cv2.morphologyEx(
        spot_mask,
        cv2.MORPH_OPEN,
        kernel_open,
        iterations=1
    )

    spot_mask = cv2.morphologyEx(
        spot_mask,
        cv2.MORPH_CLOSE,
        kernel_close,
        iterations=1
    )

    spot_mask_view = spot_mask.copy()

    result = image.copy()

    cv2.polylines(
        result,
        [work_area_points.reshape((-1, 1, 2))],
        isClosed=True,
        color=(255, 0, 0),
        thickness=2
    )

    # Вместо dark_gray_thresh теперь показываем имя изображения
    cv2.putText(
        result,
        f"Image: {get_current_image_name()}",
        (30, 50),
        cv2.FONT_HERSHEY_SIMPLEX,
        1.0,
        (0, 0, 255),
        2,
        cv2.LINE_AA
    )

    contours, _ = cv2.findContours(
        spot_mask,
        cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    found = False
    image_number = image_numbers[current_index]
    spot_id = 1

    for cnt in contours:
        area = cv2.contourArea(cnt)

        if area < min_spot_area:
            continue

        if area > max_spot_area:
            continue

        x, y, bw, bh = cv2.boundingRect(cnt)

        if bw <= 1 or bh <= 1:
            continue

        aspect = max(bw, bh) / max(1, min(bw, bh))

        # Фильтр от длинных линий и теней
        if aspect > 8:
            continue

        moments = cv2.moments(cnt)

        if moments["m00"] != 0:
            cx = int(moments["m10"] / moments["m00"])
            cy = int(moments["m01"] / moments["m00"])
        else:
            cx = x + bw // 2
            cy = y + bh // 2

        found = True

        cv2.drawContours(result, [cnt], -1, (0, 255, 0), 2)
        cv2.rectangle(result, (x, y), (x + bw, y + bh), (0, 0, 255), 2)
        cv2.circle(result, (cx, cy), 5, (255, 0, 0), -1)
        cv2.drawMarker(
            result,
            (cx, cy),
            (255, 0, 0),
            cv2.MARKER_CROSS,
            20,
            2
        )

        text = f"{spot_id}: ({cx},{cy}) S={int(area)}"

        cv2.putText(
            result,
            text,
            (x, max(25, y - 10)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 0, 255),
            2,
            cv2.LINE_AA
        )

        print(
            f"Кадр {image_number}: пятно {spot_id}, "
            f"центр=({cx}, {cy}), площадь={area:.1f}, "
            f"bbox=({x}, {y}, {bw}, {bh}), "
            f"dark_gray_thresh={dark_gray_thresh}"
        )

        spot_id += 1

    if found:
        if last_reported_image_number != image_number:
            print(f"Найден дефект на изображении: {image_number}")
            last_reported_image_number = image_number

    result_view = result


# ============================================================
# ПЕРЕСЧЕТ МАСКИ
# ============================================================

def rebuild_mask():
    global current_mask_view, image_with_area

    if image is None:
        return

    update_settings_from_trackbars()

    image_with_area = draw_work_area(image)

    work_mask = make_work_area_mask()

    if remove_yellow:
        work_mask = remove_yellow_tray_from_mask(image, work_mask)

    current_mask_view = work_mask

    detect_dark_and_gray_spots()


# ============================================================
# ЗАГРУЗКА ТЕКУЩЕГО ИЗОБРАЖЕНИЯ
# ============================================================

def load_current_image():
    global image, image_with_area, current_mask_view
    global spot_mask_view, result_view, h, w
    global last_reported_image_number, need_rebuild

    file_path = image_files[current_index]

    img = cv2.imread(file_path, cv2.IMREAD_COLOR)

    if img is None:
        print(f"Ошибка: не удалось открыть {file_path}")
        return

    image = img
    h, w = image.shape[:2]

    create_trackbars()

    image_with_area = draw_work_area(image)

    current_mask_view = np.zeros((h, w), dtype=np.uint8)
    spot_mask_view = np.zeros((h, w), dtype=np.uint8)
    result_view = image.copy()

    last_reported_image_number = None
    need_rebuild = True

    print("\n====================================")
    print(f"Открыто изображение: {file_path}")
    print(f"Размер изображения: ширина={w}, высота={h}")
    print("====================================")

    rebuild_mask()


# ============================================================
# ПЕРЕХОД К СЛЕДУЮЩЕМУ ИЗОБРАЖЕНИЮ
# ============================================================

def next_image():
    global current_index

    current_index += 1

    if current_index >= len(image_files):
        current_index = 0

    load_current_image()


# ============================================================
# ОБРАБОТКА МЫШИ
# ============================================================

def mouse_callback(event, x, y, flags, param):
    if event == cv2.EVENT_LBUTTONDOWN:
        print(f"Координаты точки: [{x}, {y}]")


# ============================================================
# ОСНОВНАЯ ПРОГРАММА
# ============================================================

cv2.namedWindow("1 Image with work area", cv2.WINDOW_NORMAL)
cv2.namedWindow("2 Work area mask", cv2.WINDOW_NORMAL)
cv2.namedWindow("3 Dark spot mask", cv2.WINDOW_NORMAL)
cv2.namedWindow("4 Result with spot centers", cv2.WINDOW_NORMAL)

cv2.setMouseCallback("1 Image with work area", mouse_callback)

load_current_image()

last_switch_time = time.time()

while True:
    if need_rebuild:
        need_rebuild = False
        rebuild_mask()

    if image_with_area is not None:
        cv2.imshow("1 Image with work area", image_with_area)

    if current_mask_view is not None:
        cv2.imshow("2 Work area mask", current_mask_view)

    if spot_mask_view is not None:
        cv2.imshow("3 Dark spot mask", spot_mask_view)

    if result_view is not None:
        cv2.imshow("4 Result with spot centers", result_view)

    now = time.time()

    if (now - last_switch_time) * 1000 >= t:
        next_image()
        last_switch_time = now

    key = cv2.waitKey(1) & 0xFF

    # ESC — выход
    if key == 27:
        break

    # Пробел — ручной переход к следующему изображению
    if key == 32:
        next_image()
        last_switch_time = time.time()

    # S — вывести текущие настройки в консоль
    if key == ord("s") or key == ord("S"):
        print_current_settings()

cv2.destroyAllWindows()