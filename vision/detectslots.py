import cv2
import requests
import time
import json
import numpy as np
from ultralytics import YOLO

BACKEND_URL     = "https://arkasense.onrender.com/update-slots"
CAMERA_INDEX    = 0
UPDATE_INTERVAL = 1

# How many consecutive frames before a status change is accepted
DEBOUNCE_FRAMES = 5

# ─────────────────────────────────────────
# Load slot zones from zones.json
# ─────────────────────────────────────────
try:
    with open("zones.json", "r") as f:
        raw = json.load(f)
    SLOT_ZONES  = {k: tuple(v) for k, v in raw.items()}
    TOTAL_SLOTS = len(SLOT_ZONES)
    print(f"Loaded {TOTAL_SLOTS} slot zones:")
    for name, zone in SLOT_ZONES.items():
        print(f"  {name}: x={zone[0]}, y={zone[1]}, w={zone[2]}, h={zone[3]}")
except FileNotFoundError:
    print("zones.json not found! Run calibrate.py first.")
    exit()

# ─────────────────────────────────────────
# Load YOLO
# ─────────────────────────────────────────
print("\nLoading YOLOv8 model...")
model = YOLO("yolov8n.pt")
print("YOLOv8 ready!\n")

# COCO classes to treat as occupying a slot
ANY_CLASSES = {
    0, 2, 3, 5, 7,           # person, car, motorcycle, bus, truck
    39, 41, 56, 57, 58,      # bottle, cup, chair, couch, plant
    63, 64, 65, 66, 67,      # laptop, mouse, keyboard, phone
    72, 73, 76               # tv, book, scissors
}


def overlap_ratio(box, zone):
    """Fraction of zone area covered by a detected box."""
    bx1, by1, bx2, by2 = box
    zx, zy, zw, zh = zone
    zx2, zy2 = zx + zw, zy + zh

    ix1 = max(bx1, zx);  iy1 = max(by1, zy)
    ix2 = min(bx2, zx2); iy2 = min(by2, zy2)

    if ix2 <= ix1 or iy2 <= iy1:
        return 0.0

    inter     = (ix2 - ix1) * (iy2 - iy1)
    zone_area = zw * zh
    return inter / zone_area if zone_area > 0 else 0.0


def pixel_darkness(frame, zone, threshold=70):
    """
    Fallback for top-down cameras:
    Cars seen from above are often darker than an empty concrete slot.
    Also checks texture/variance — parked cars have more edges.
    """
    x, y, w, h = zone
    pad = 6
    roi = frame[y+pad : y+h-pad, x+pad : x+w-pad]
    if roi.size == 0:
        return False
    gray     = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    mean_v   = np.mean(gray)
    variance = np.var(gray)
    # Dark AND high texture = something is there
    return mean_v < threshold and variance > 200


def is_occupied_by_yolo(detected_boxes, zone):
    """True if any detection overlaps this zone by >=15% OR centre is inside."""
    for box in detected_boxes:
        if overlap_ratio(box, zone) >= 0.15:
            return True
        cx = (box[0] + box[2]) / 2
        cy = (box[1] + box[3]) / 2
        zx, zy, zw, zh = zone
        if (zx < cx < zx + zw) and (zy < cy < zy + zh):
            return True
    return False


def send_to_backend(slot_status):
    try:
        r = requests.post(BACKEND_URL, json={
            "slots":     slot_status,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }, timeout=2)
        data      = r.json()
        available = data.get('available', '?')
        print(f"Sent → Available: {available}/{TOTAL_SLOTS} | {slot_status}")
    except Exception as e:
        print(f"Backend not reachable: {e}")


def draw_overlay(frame, stable_status):
    for slot_name, zone in SLOT_ZONES.items():
        x, y, w, h = zone
        is_free = stable_status[slot_name] == "free"
        color   = (0, 255, 135) if is_free else (0, 0, 255)

        overlay = frame.copy()
        cv2.rectangle(overlay, (x, y), (x+w, y+h), color, -1)
        cv2.addWeighted(overlay, 0.18, frame, 0.82, 0, frame)
        cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)

        label = f"{slot_name}: {'FREE' if is_free else 'TAKEN'}"
        cv2.putText(frame, label, (x, y - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 2)

        dot_color = (0, 255, 0) if is_free else (0, 0, 255)
        cv2.circle(frame, (x + w//2, y + h//2), 8, dot_color, -1)

    available = sum(1 for s in stable_status.values() if s == "free")
    bar_color = (0, 200, 100) if available > 0 else (0, 0, 220)
    cv2.rectangle(frame, (0, 0), (frame.shape[1], 36), (10, 14, 26), -1)
    cv2.putText(frame,
                f"ParkaSense  |  Available: {available}/{TOTAL_SLOTS}  |  Q = quit  |  {time.strftime('%H:%M:%S')}",
                (10, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.6, bar_color, 2)
    return frame


def run_detection():
    cap = cv2.VideoCapture(CAMERA_INDEX)
    if not cap.isOpened():
        print("Cannot open webcam. Try changing CAMERA_INDEX to 1")
        return

    print(f"Webcam opened! Detecting {TOTAL_SLOTS} slots... Press Q to quit\n")

    last_update   = 0
    last_sent     = {name: "free" for name in SLOT_ZONES}
    raw_status    = {name: "free" for name in SLOT_ZONES}
    stable_status = {name: "free" for name in SLOT_ZONES}
    counters      = {name: 0      for name in SLOT_ZONES}

    while True:
        ret, frame = cap.read()
        if not ret:
            print("Cannot read frame. Retrying...")
            time.sleep(1)
            continue

        # Low confidence threshold — better for top-down angles
        results = model.predict(frame, conf=0.10, verbose=False)

        detected_boxes = []
        for result in results:
            for box in result.boxes:
                cls = int(box.cls[0])
                if cls in ANY_CLASSES:
                    detected_boxes.append(box.xyxy[0].tolist())

        # ── Per-slot check: YOLO + pixel darkness fallback ──
        for slot_name, zone in SLOT_ZONES.items():
            yolo_hit     = is_occupied_by_yolo(detected_boxes, zone)
            darkness_hit = pixel_darkness(frame, zone, threshold=70)

            new_raw = "occupied" if (yolo_hit or darkness_hit) else "free"

            if new_raw == raw_status[slot_name]:
                counters[slot_name] += 1
            else:
                raw_status[slot_name] = new_raw
                counters[slot_name]   = 1

            # Only accept change after DEBOUNCE_FRAMES consistent frames
            if counters[slot_name] >= DEBOUNCE_FRAMES:
                stable_status[slot_name] = raw_status[slot_name]

        frame = draw_overlay(frame, stable_status)

        now = time.time()
        if now - last_update >= UPDATE_INTERVAL:
            if stable_status != last_sent or (now - last_update >= 5):
                send_to_backend(stable_status)
                last_sent   = stable_status.copy()
                last_update = now

        cv2.imshow("ParkaSense — Live Detection", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            print("Quitting...")
            break

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    run_detection()
