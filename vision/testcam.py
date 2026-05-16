"""Simple camera tester for the arkasense vision folder.

Usage examples:
  python testcam.py --source 0
  python testcam.py --source rtsp://user:pass@host:554/stream --no-display --save-dir samples

Options:
  --source     Camera source (index, file path, or URL). Defaults to 0.
  --width      Requested capture width.
  --height     Requested capture height.
  --no-display Do not open a preview window.
  --save-dir   Directory to save frames when pressing 's'.
  --save-single Save the first frame then exit.
  --timeout    Stop after N seconds (0 = no timeout).
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import cv2


def parse_args() -> argparse.Namespace:
	p = argparse.ArgumentParser(description="Camera test utility")
	p.add_argument("--source", default="0", help="camera index, file path or URL")
	p.add_argument("--width", type=int, default=0)
	p.add_argument("--height", type=int, default=0)
	p.add_argument("--no-display", action="store_true")
	p.add_argument("--save-dir", default=None, help="directory to save frames when pressing 's'")
	p.add_argument("--save-single", action="store_true", help="save the first frame then exit")
	p.add_argument("--backend", default="any", choices=["any", "dshow", "msmf", "ffmpeg", "gstreamer", "v4l2"], help="preferred OpenCV backend or 'any' to try several")
	p.add_argument("--probe", action="store_true", help="probe camera indices (and backends) and exit")
	p.add_argument("--probe-max", type=int, default=4, help="maximum camera index to probe (0..N)")
	p.add_argument("--timeout", type=float, default=0.0, help="stop after N seconds (0 = run forever)")
	return p.parse_args()


def _backend_const(name: str):
	mapping = {
		"dshow": getattr(cv2, "CAP_DSHOW", 700),
		"msmf": getattr(cv2, "CAP_MSMF", 140),
		"ffmpeg": getattr(cv2, "CAP_FFMPEG", 1900),
		"gstreamer": getattr(cv2, "CAP_GSTREAMER", 1800),
		"v4l2": getattr(cv2, "CAP_V4L2", 2000),
	}
	return mapping.get(name)


def open_capture(source: str, backend: str = "any"):
	src = int(source) if source.isdigit() else source

	tried = []
	backends_to_try = []
	if backend != "any":
		const = _backend_const(backend)
		backends_to_try = [const] if const is not None else [0]
	else:
		# prefer Windows-friendly backends first
		backends_to_try = [
			_backend_const("dshow"),
			_backend_const("msmf"),
			_backend_const("ffmpeg"),
			0,  # default
		]

	for b in backends_to_try:
		try:
			if isinstance(b, int) and b != 0:
				cap = cv2.VideoCapture(src, int(b))
			else:
				cap = cv2.VideoCapture(src)
		except Exception:
			cap = cv2.VideoCapture(src)

		tried.append(b)
		if cap.isOpened():
			print(f"Opened source={source} with backend={b}")
			return cap
		else:
			cap.release()

	raise RuntimeError(f"Cannot open video source: {source} (tried backends: {tried})")


def probe_devices(max_index: int = 4, backends: list | None = None):
	if backends is None:
		backends = ["dshow", "msmf", "ffmpeg", "default"]
	results = []
	for i in range(0, max_index + 1):
		for b in backends:
			try:
				if b == "default":
					cap = cv2.VideoCapture(i)
				else:
					const = _backend_const(b)
					cap = cv2.VideoCapture(i, int(const)) if const is not None else cv2.VideoCapture(i)

				ok = cap.isOpened()
				cap.release()
			except Exception:
				ok = False
			results.append((i, b, ok))
			status = "OK" if ok else "--"
			print(f"Index {i:02d}  backend={b:8s}  {status}")
	return results


def save_frame(frame, save_dir: Optional[Path]):
	if save_dir is None:
		return None
	save_dir.mkdir(parents=True, exist_ok=True)
	ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
	path = save_dir / f"frame_{ts}.png"
	cv2.imwrite(str(path), frame)
	return path


def run():
	args = parse_args()
	save_dir = Path(args.save_dir) if args.save_dir else None

	if args.probe:
		probe_devices(args.probe_max)
		return

	cap = open_capture(args.source, backend=args.backend)
	if args.width > 0:
		cap.set(cv2.CAP_PROP_FRAME_WIDTH, args.width)
	if args.height > 0:
		cap.set(cv2.CAP_PROP_FRAME_HEIGHT, args.height)

	window_name = "TestCam"
	if not args.no_display:
		cv2.namedWindow(window_name, cv2.WINDOW_NORMAL)

	start_time = time.time()
	frames_total = 0
	frames_since = 0
	last_fps_time = start_time
	fps = 0.0

	try:
		while True:
			ret, frame = cap.read()
			if not ret:
				print("Frame read failed — stopping")
				break

			frames_total += 1
			frames_since += 1
			now = time.time()

			elapsed_since = now - last_fps_time
			if elapsed_since >= 0.5:
				fps = frames_since / elapsed_since if elapsed_since > 0 else 0.0
				frames_since = 0
				last_fps_time = now

			overlay = f"Frames: {frames_total}  FPS: {fps:.2f}"
			cv2.putText(frame, overlay, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 0), 2)

			if not args.no_display:
				cv2.imshow(window_name, frame)

			if args.save_single:
				saved = save_frame(frame, save_dir)
				print("Saved:", saved)
				break

			key = cv2.waitKey(1) & 0xFF
			if key == ord("q"):
				break
			if key == ord("s"):
				saved = save_frame(frame, save_dir)
				print("Saved:", saved)

			if args.timeout > 0 and (now - start_time) >= args.timeout:
				print("Timeout reached — stopping")
				break

	except KeyboardInterrupt:
		pass
	finally:
		cap.release()
		if not args.no_display:
			cv2.destroyAllWindows()


if __name__ == "__main__":
	run()

