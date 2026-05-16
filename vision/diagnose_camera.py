"""Windows camera diagnostic helper.

Usage:
  python diagnose_camera.py

What it does:
  - Queries Windows for PnP devices that look like cameras (PowerShell)
  - Attempts to open camera indices 0..N with several OpenCV backends
  - Tries opening by device name using DirectShow "video=<name>" syntax

This requires Python and OpenCV. It uses PowerShell (available on modern Windows).
"""

from __future__ import annotations

import json
import shlex
import subprocess
import sys
from typing import List

import cv2


def run_powershell_json(cmd: str) -> List[dict]:
    full = [
        "powershell",
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        cmd,
    ]
    try:
        proc = subprocess.run(full, capture_output=True, text=True, check=True)
        out = proc.stdout.strip()
        if not out:
            return []
        return json.loads(out)
    except subprocess.CalledProcessError as e:
        print("PowerShell command failed:", e)
        if e.stdout:
            print(e.stdout)
        if e.stderr:
            print(e.stderr)
        return []
    except json.JSONDecodeError:
        # PowerShell may return a single object, not an array
        try:
            return [json.loads(proc.stdout.strip())]
        except Exception:
            return []


def list_pnp_cameras() -> List[dict]:
    # Try a CIM query filtering by name keywords and output JSON
    ps = (
        "Get-CimInstance Win32_PnPEntity | Where-Object { $_.Name -match 'camera|imaging|webcam|usb' } "
        "| Select-Object Name,PNPDeviceID,Status | ConvertTo-Json"
    )
    results = run_powershell_json(ps)
    if not results:
        # fallback to Get-PnpDevice (newer PowerShell)
        ps2 = (
            "Get-PnpDevice -Class Camera | Select-Object FriendlyName,InstanceId,Status | ConvertTo-Json"
        )
        results = run_powershell_json(ps2)
    return results


def try_open_indices(max_index: int = 6):
    print("\nProbing indices with backends:")
    backends = []
    if hasattr(cv2, "CAP_DSHOW"):
        backends.append(("dshow", cv2.CAP_DSHOW))
    if hasattr(cv2, "CAP_MSMF"):
        backends.append(("msmf", cv2.CAP_MSMF))
    if hasattr(cv2, "CAP_FFMPEG"):
        backends.append(("ffmpeg", cv2.CAP_FFMPEG))
    backends.append(("default", None))

    for i in range(0, max_index + 1):
        for name, b in backends:
            try:
                if b is None:
                    cap = cv2.VideoCapture(i)
                else:
                    cap = cv2.VideoCapture(i, int(b))
                ok = cap.isOpened()
                cap.release()
            except Exception:
                ok = False
            print(f"Index {i:02d}  backend={name:8s}  {'OK' if ok else '--'})")


def try_open_by_name(names: List[str]):
    if not names:
        return
    print("\nAttempting to open by DirectShow name (video=<name>):")
    for n in names:
        try_name = f"video={n}"
        try:
            cap = cv2.VideoCapture(try_name, int(getattr(cv2, 'CAP_DSHOW', 700)))
            ok = cap.isOpened()
            cap.release()
        except Exception:
            ok = False
        print(f"Name: {n!r}  -> {'OK' if ok else '--'})")


def main():
    print("Camera diagnostic helper")

    cams = list_pnp_cameras()
    if cams:
        print("\nDetected PnP camera-like devices (from PowerShell):")
        names = []
        for c in cams:
            # The property names may vary depending on which PS query succeeded
            n = c.get("Name") or c.get("FriendlyName") or c.get("DeviceName")
            pid = c.get("PNPDeviceID") or c.get("InstanceId")
            status = c.get("Status")
            print(f"- {n}  | {pid}  | status={status}")
            if n:
                names.append(n)
    else:
        print("No camera devices found via PowerShell.")
        names = []

    try_open_indices(6)
    try_open_by_name(names)

    print("\nIf nothing opens: ensure camera drivers/SDK are installed, close other apps, or install ffmpeg to list DirectShow devices:\n  https://ffmpeg.org/download.html")


if __name__ == '__main__':
    main()
