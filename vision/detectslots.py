import cv2
import requests
import time
import json
from ultralytics import YOLO

BACKEND_URL = "https://arkasense.onrender.com/update-slots"
CAMERA_INDEX    = 0
UPDATE_INTERVAL = 1

# Load slot zones
try:
    with open("zones.json", "r") as f:
        raw = json.load(f)
    SLOT_ZONES = {k: tuple(v) for k, v in raw.items()}
    print("Loaded slot zones:")
    for name, zone in SLOT_ZONES.items():
        print(f"  {name}: x={zone[0]}, y={zone[1]}, w={zone[2]}, h={zone[3]}")
except FileNotFoundError:
    print("zones.json not found! Run calibrate.py first.")
    exit()

# Load YOLO
print("\nLoading YOLOv8 model...")
model = YOLO("yolov8n.pt")
print("YOLOv8 ready!\n")

# YOLO COCO classes to detect as "occupied"
# 0=person, 2=car, 3=motorcycle, 5=bus, 7=truck
# 39=bottle, 41=cup, 67=phone, 73=book, 76=scissors
DETECT_CLASSES = {0, 2, 3, 5, 7, 39, 41, 67, 73, 76}

def is_in_zone(box, zone):
    cx1, cy1, cx2, cy2 = box
    zx, zy, zw, zh = zone
    zx2 = zx + zw
    zy2 = zy + zh
    obj_cx = (cx1 + cx2) / 2
    obj_cy = (cy1 + cy2) / 2
    return (zx < obj_cx < zx2) and (zy < obj_cy < zy2)

def send_to_backend(slot_status):
    try:
        r = requests.post(BACKEND_URL, json={
            "slots": slot_status,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }, timeout=2)
        data = r.json()
        print(f"Sent -> Available: {data.get('available','?')}/3 | {slot_status}")
    except Exception as e:
        print(f"Backend not reachable: {e}")

def draw_overlay(frame, slot_status):
    for slot_name, zone in SLOT_ZONES.items():
        x, y, w, h = zone
        is_free = slot_status[slot_name] == "free"
        color = (0, 255, 135) if is_free else (0, 0, 255)
        cv2.rectangle(frame, (x, y), (x + w, y + h), color, 2)
        overlay = frame.copy()
        cv2.rectangle(overlay, (x, y), (x + w, y + h), color, -1)
        cv2.addWeighted(overlay, 0.15, frame, 0.85, 0, frame)
        label = f"{slot_name}: {'FREE' if is_free else 'TAKEN'}"
        cv2.putText(frame, label, (x, y - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)
        dot_color = (0, 255, 0) if is_free else (0, 0, 255)
        cv2.circle(frame, (x + w // 2, y + h // 2), 8, dot_color, -1)
    available = sum(1 for s in slot_status.values() if s == "free")
    cv2.rectangle(frame, (0, 0), (frame.shape[1], 36), (10, 14, 26), -1)
    bar_color = (0, 200, 100) if available > 0 else (0, 0, 220)
    cv2.putText(frame,
                f"ParkaSense ECA  |  Available: {available}/3  |  Press Q to quit",
                (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, bar_color, 2)
    return frame

def run_detection():
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print("Cannot open webcam. Try changing CAMERA_INDEX to 1")
        return

    print("Webcam opened successfully!")
    print("Detecting... Press Q in the window to quit\n")

    last_update = 0
    last_status = {name: "free" for name in SLOT_ZONES}

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Cannot read frame. Retrying...")
            time.sleep(1)
            continue

        results = model.predict(frame, conf=0.15, verbose=False)

        detected_boxes = []
        for result in results:
            for box in result.boxes:
                cls = int(box.cls[0])
                if cls in DETECT_CLASSES:
                    detected_boxes.append(box.xyxy[0].tolist())

        slot_status = {}
        for slot_name, zone in SLOT_ZONES.items():
            occupied = any(is_in_zone(b, zone) for b in detected_boxes)
            slot_status[slot_name] = "occupied" if occupied else "free"

        frame = draw_overlay(frame, slot_status)

        now = time.time()
        if now - last_update >= UPDATE_INTERVAL:
            if slot_status != last_status or (now - last_update >= 5):
                send_to_backend(slot_status)
                last_status = slot_status.copy()
                last_update = now

        cv2.imshow("ParkaSense ECA - Live Detection", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("Quitting...")
            break

    cap.release()
    cv2.destroyAllWindows()

if __name__ == "__main__":
    run_detection()