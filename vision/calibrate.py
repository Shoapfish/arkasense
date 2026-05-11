import cv2
import json

# ─────────────────────────────────────────
# PARKASENSE — 6 Slot Zone Calibrator
# Instructions:
#   1. Run this script
#   2. A window opens showing your webcam
#   3. Click TOP-LEFT then BOTTOM-RIGHT of each slot
#   4. Do this for all 6 slots S1-S6
#   5. Press S to save, R to reset, Q to quit
# ─────────────────────────────────────────

CAMERA_INDEX = 0

slots = {}
clicks = []
current_slot = 0
slot_names = ["S1", "S2", "S3", "S4", "S5", "S6"]
colors = {
    "S1": (0, 255, 135),
    "S2": (0, 215, 255),
    "S3": (255, 144, 74),
    "S4": (255, 0, 128),
    "S5": (180, 0, 255),
    "S6": (0, 200, 255),
}

def draw_instructions(frame, current_slot, clicks):
    h, w = frame.shape[:2]
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 60), (10, 14, 26), -1)
    cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)

    if current_slot < 6:
        slot_name = slot_names[current_slot]
        color = colors[slot_name]
        if len(clicks) % 2 == 0:
            msg = f"Click TOP-LEFT corner of slot {slot_name}  ({current_slot+1}/6)"
        else:
            msg = f"Click BOTTOM-RIGHT corner of slot {slot_name}  ({current_slot+1}/6)"
        cv2.putText(frame, msg, (10, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    else:
        cv2.putText(frame, "All 6 slots marked! Press S to SAVE or R to RESET",
                    (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 135), 2)

    # Progress bar
    progress = int((current_slot / 6) * 400)
    cv2.rectangle(frame, (10, 50), (410, 58), (30, 40, 60), -1)
    cv2.rectangle(frame, (10, 50), (10 + progress, 58), (0, 255, 135), -1)

    cv2.putText(frame, "R=Reset  S=Save  Q=Quit",
                (10, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (74, 96, 128), 1)

def draw_slots(frame, slots, clicks, current_slot):
    for name, (x1, y1, x2, y2) in slots.items():
        color = colors[name]
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        overlay = frame.copy()
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)
        cv2.addWeighted(overlay, 0.15, frame, 0.85, 0, frame)
        cx = (x1 + x2) // 2
        cy = (y1 + y2) // 2
        cv2.putText(frame, name, (cx - 15, cy + 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

    if len(clicks) % 2 == 1 and current_slot < 6:
        cx, cy = clicks[-1]
        name = slot_names[current_slot]
        color = colors[name]
        cv2.circle(frame, (cx, cy), 6, color, -1)
        cv2.putText(frame, "P1", (cx + 8, cy - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

def mouse_callback(event, x, y, flags, param):
    global clicks, current_slot, slots

    if event == cv2.EVENT_LBUTTONDOWN:
        if current_slot >= 6:
            return

        clicks.append((x, y))

        if len(clicks) % 2 == 0:
            p1 = clicks[-2]
            p2 = clicks[-1]
            name = slot_names[current_slot]
            x1, y1 = min(p1[0], p2[0]), min(p1[1], p2[1])
            x2, y2 = max(p1[0], p2[0]), max(p1[1], p2[1])
            slots[name] = (x1, y1, x2, y2)
            print(f"✓ {name} defined: ({x1},{y1}) → ({x2},{y2})")
            current_slot += 1

cap = cv2.VideoCapture(CAMERA_INDEX)
if not cap.isOpened():
    print("Cannot open webcam. Try CAMERA_INDEX = 1")
    exit()

cv2.namedWindow("ParkaSense Calibrator — 6 Slots")
cv2.setMouseCallback("ParkaSense Calibrator — 6 Slots", mouse_callback)

print("=" * 50)
print("PARKASENSE 6-SLOT CALIBRATOR")
print("=" * 50)
print("Mark all 6 slots: S1 S2 S3 (top row)")
print("                  S4 S5 S6 (bottom row)")
print("Click TOP-LEFT then BOTTOM-RIGHT for each")
print("=" * 50)

while True:
    ret, frame = cap.read()
    if not ret:
        print("Cannot read webcam frame")
        break

    draw_slots(frame, slots, clicks, current_slot)
    draw_instructions(frame, current_slot, clicks)
    cv2.imshow("ParkaSense Calibrator — 6 Slots", frame)

    key = cv2.waitKey(1) & 0xFF

    if key == ord('q'):
        print("Quit without saving.")
        break

    elif key == ord('r'):
        slots = {}
        clicks = []
        current_slot = 0
        print("Reset! Start from S1 again.")

    elif key == ord('s'):
        if len(slots) < 6:
            print(f"Only {len(slots)}/6 slots marked. Mark all 6 first!")
            continue

        output = {}
        for name, (x1, y1, x2, y2) in slots.items():
            output[name] = (x1, y1, x2 - x1, y2 - y1)

        with open("zones.json", "w") as f:
            json.dump(output, f, indent=2)

        print("\n" + "=" * 50)
        print("✅ SAVED to zones.json — 6 slots!")
        print("=" * 50)
        for name, (x, y, w, h) in output.items():
            print(f"  {name}: x={x}, y={y}, w={w}, h={h}")
        print("\nNow run: python detectslots.py")
        break

cap.release()
cv2.destroyAllWindows()