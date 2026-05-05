import cv2
import json

# ─────────────────────────────────────────
# PARKASENSE — Slot Zone Calibrator
# Instructions:
#   1. Run this script
#   2. A window opens showing your webcam
#   3. Click TOP-LEFT corner of slot S1, then BOTTOM-RIGHT corner of S1
#   4. Repeat for S2 and S3
#   5. Press S to save when all 3 slots are marked
#   6. Press R to reset and start over
# ─────────────────────────────────────────

CAMERA_INDEX = 0  # change to 1 if webcam not found

slots = {}
clicks = []
current_slot = 0
slot_names = ["S1", "S2", "S3"]
colors = {
    "S1": (0, 255, 135),   # green
    "S2": (255, 215, 0),   # gold
    "S3": (0, 180, 255),   # blue
}

def draw_instructions(frame, current_slot, clicks):
    h, w = frame.shape[:2]
    overlay = frame.copy()
    cv2.rectangle(overlay, (0, 0), (w, 60), (10, 14, 26), -1)
    cv2.addWeighted(overlay, 0.8, frame, 0.2, 0, frame)

    if current_slot < 3:
        slot_name = slot_names[current_slot]
        color = colors[slot_name]
        if len(clicks) % 2 == 0:
            msg = f"Click TOP-LEFT corner of slot {slot_name}"
        else:
            msg = f"Click BOTTOM-RIGHT corner of slot {slot_name}"
        cv2.putText(frame, msg, (10, 35),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
    else:
        cv2.putText(frame, "All slots marked! Press S to SAVE or R to RESET",
                    (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.65, (0, 255, 135), 2)

    # Bottom hint
    cv2.putText(frame, "R = Reset   S = Save   Q = Quit",
                (10, h - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (74, 96, 128), 1)

def draw_slots(frame, slots, clicks, current_slot):
    # Draw completed slots
    for name, (x1, y1, x2, y2) in slots.items():
        color = colors[name]
        cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
        # Fill with transparent color
        overlay = frame.copy()
        cv2.rectangle(overlay, (x1, y1), (x2, y2), color, -1)
        cv2.addWeighted(overlay, 0.15, frame, 0.85, 0, frame)
        # Label
        cv2.putText(frame, name, (x1 + 8, y1 + 28),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, color, 2)

    # Draw first click point if waiting for second
    if len(clicks) % 2 == 1 and current_slot < 3:
        cx, cy = clicks[-1]
        name = slot_names[current_slot]
        color = colors[name]
        cv2.circle(frame, (cx, cy), 5, color, -1)
        cv2.putText(frame, "P1", (cx + 8, cy - 8),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

def mouse_callback(event, x, y, flags, param):
    global clicks, current_slot, slots

    if event == cv2.EVENT_LBUTTONDOWN:
        if current_slot >= 3:
            return

        clicks.append((x, y))

        # Every 2 clicks = one slot defined
        if len(clicks) % 2 == 0:
            p1 = clicks[-2]
            p2 = clicks[-1]
            name = slot_names[current_slot]
            # Normalize so top-left is always smaller
            x1, y1 = min(p1[0], p2[0]), min(p1[1], p2[1])
            x2, y2 = max(p1[0], p2[0]), max(p1[1], p2[1])
            slots[name] = (x1, y1, x2, y2)
            print(f"✓ {name} defined: ({x1},{y1}) → ({x2},{y2})")
            current_slot += 1

cap = cv2.VideoCapture(CAMERA_INDEX)
if not cap.isOpened():
    print("Cannot open webcam. Try changing CAMERA_INDEX to 1")
    exit()

cv2.namedWindow("ParkaSense Calibrator")
cv2.setMouseCallback("ParkaSense Calibrator", mouse_callback)

print("=" * 50)
print("PARKASENSE SLOT CALIBRATOR")
print("=" * 50)
print("Point your webcam at the cardboard parking lot")
print("Then click to mark each slot zone")
print("=" * 50)

while True:
    ret, frame = cap.read()
    if not ret:
        print("Cannot read webcam frame")
        break

    draw_slots(frame, slots, clicks, current_slot)
    draw_instructions(frame, current_slot, clicks)

    cv2.imshow("ParkaSense Calibrator", frame)

    key = cv2.waitKey(1) & 0xFF

    if key == ord('q'):
        print("Quit without saving.")
        break

    elif key == ord('r'):
        slots = {}
        clicks = []
        current_slot = 0
        print("Reset! Start clicking again.")

    elif key == ord('s'):
        if len(slots) < 3:
            print(f"Only {len(slots)} slots marked. Mark all 3 first!")
            continue

        # Convert to the format detectslots.py expects: (x, y, w, h)
        output = {}
        for name, (x1, y1, x2, y2) in slots.items():
            output[name] = (x1, y1, x2 - x1, y2 - y1)

        # Save to zones.json
        with open("zones.json", "w") as f:
            json.dump(output, f, indent=2)

        print("\n" + "=" * 50)
        print("✅ SAVED to zones.json!")
        print("=" * 50)
        for name, (x, y, w, h) in output.items():
            print(f"  {name}: x={x}, y={y}, w={w}, h={h}")
        print("\nNow run: python detectslots.py")
        break

cap.release()
cv2.destroyAllWindows()
