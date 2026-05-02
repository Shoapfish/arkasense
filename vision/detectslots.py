import cv2
import requests
import time
from ultralytics import YOLO

# ─────────────────────────────────────────
#  CONFIGURATION — edit these values
# ─────────────────────────────────────────

# Backend server URL (we'll set this up next)
BACKEND_URL = "http://localhost:3000/update-slots"

# 0 = first webcam. Change to 1 if webcam not found later.
CAMERA_INDEX = 0

# How many seconds between each detection update
UPDATE_INTERVAL = 1

# ─────────────────────────────────────────
#  SLOT ZONES — pixel coordinates [x, y, w, h]
#  These define where each slot is in the frame.
#  We'll calibrate these once you have the webcam.
#  For now these are placeholders.
# ─────────────────────────────────────────
SLOT_ZONES = {
    "S1": (50,  100, 150, 200),  # (x, y, width, height)
    "S2": (220, 100, 150, 200),
    "S3": (390, 100, 150, 200),
}

# ─────────────────────────────────────────
#  LOAD YOLO MODEL
#  yolov8n = nano (smallest + fastest, perfect for demo)
# ─────────────────────────────────────────
print("Loading YOLOv8 model...")
model = YOLO("yolov8n.pt")  # auto-downloads on first run
print("Model loaded! Starting detection...")

# ─────────────────────────────────────────
#  HELPER: check if a detected car overlaps a slot zone
# ─────────────────────────────────────────
def is_car_in_zone(car_box, zone):
    cx1, cy1, cx2, cy2 = car_box          # car bounding box
    zx, zy, zw, zh     = zone             # slot zone
    zx2, zy2           = zx + zw, zy + zh # zone bottom-right

    # Check if centers overlap (overlap detection)
    car_cx = (cx1 + cx2) / 2
    car_cy = (cy1 + cy2) / 2

    return (zx < car_cx < zx2) and (zy < car_cy < zy2)

# ─────────────────────────────────────────
#  HELPER: send slot status to backend
# ─────────────────────────────────────────
def send_to_backend(slot_status):
    try:
        requests.post(BACKEND_URL, json={
            "slots": slot_status,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }, timeout=2)
        print(f"Sent: {slot_status}")
    except Exception as e:
        print(f"Backend not ready yet: {e}")

# ─────────────────────────────────────────
#  MAIN LOOP
# ─────────────────────────────────────────
def run_detection():
    cap = cv2.VideoCapture(CAMERA_INDEX)
    last_update = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            print("No webcam found. Waiting...")
            time.sleep(2)
            continue

        # Run YOLO — detect all objects in frame
        results = model.predict(frame, conf=0.3, verbose=False)

        # Get all car bounding boxes (class 2 = car in COCO dataset)
        car_boxes = []
        for result in results:
            for box in result.boxes:
                if int(box.cls) == 2:  # 2 = car
                    car_boxes.append(box.xyxy[0].tolist())

        # Check each slot zone against detected cars
        slot_status = {}
        for slot_name, zone in SLOT_ZONES.items():
            occupied = any(is_car_in_zone(car, zone) for car in car_boxes)
            slot_status[slot_name] = "occupied" if occupied else "free"

            # Draw slot zone on frame (green=free, red=occupied)
            x, y, w, h = zone
            color = (0, 255, 0) if not occupied else (0, 0, 255)
            cv2.rectangle(frame, (x, y), (x+w, y+h), color, 2)
            cv2.putText(frame, f"{slot_name}: {slot_status[slot_name]}",
                        (x, y-10), cv2.FONT_HERSHEY_SIMPLEX,
                        0.6, color, 2)

        # Send update every UPDATE_INTERVAL seconds
        if time.time() - last_update >= UPDATE_INTERVAL:
            send_to_backend(slot_status)
            last_update = time.time()

        # Show the live annotated frame
        cv2.imshow("ParkaSense - Slot Detection", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break

    cap.release()
    cv2.destroyAllWindows()

# Entry point
if __name__ == "__main__":
    run_detection()