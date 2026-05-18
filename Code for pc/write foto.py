import os
import cv2

save_folder = r"C:\Users\L13 Yoga\Documents\foto1080"
os.makedirs(save_folder, exist_ok=True)

cap = cv2.VideoCapture(1, cv2.CAP_DSHOW)

if not cap.isOpened():
    raise RuntimeError("Камера 1 не открылась")

i = 0
while i < 1000:
    ret, img = cap.read()

    if not ret:
        print(f"Ошибка чтения кадра {i}")
        break

    filename = os.path.join(save_folder, f"{i}.png")
    cv2.imwrite(filename, img)
    print(f"Сохранён кадр {i}")

    i += 1

cap.release()
cv2.destroyAllWindows()