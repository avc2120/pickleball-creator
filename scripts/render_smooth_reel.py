import cv2
import json
import os
import sys
import numpy as np

input_path = sys.argv[1]
points_path = sys.argv[2]
frames_dir = sys.argv[3]

with open(points_path, "r") as f:
    points = json.load(f)["points"]

cap = cv2.VideoCapture(input_path)
if not cap.isOpened():
    raise RuntimeError(f"Failed to open input video: {input_path}")

fps = cap.get(cv2.CAP_PROP_FPS) or 30
w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

out_w, out_h = 1080, 1920
scale = max(out_w / w, out_h / h)
scaled_w = int(np.ceil(w * scale))
scaled_h = int(np.ceil(h * scale))


os.makedirs(frames_dir, exist_ok=True)

times = np.array([p["t"] for p in points]) if points else np.array([])
centers = np.array([p["centerX"] for p in points]) if points else np.array([])

frame_idx = 0
last_crop_x = None
alpha = 0.12

while True:
    ret, frame = cap.read()
    if not ret:
        break

    t = frame_idx / fps
    center_x = np.interp(t, times, centers) if len(points) > 1 else w / 2

    scaled = cv2.resize(frame, (scaled_w, scaled_h))

    target_crop_x = int(center_x - out_w / 2)
    target_crop_x = max(0, min(scaled_w - out_w, target_crop_x))

    if last_crop_x is None:
        crop_x = target_crop_x
    else:
        crop_x = int(alpha * target_crop_x + (1 - alpha) * last_crop_x)

    last_crop_x = crop_x

    cropped = scaled[0:out_h, crop_x:crop_x + out_w]

    cv2.imwrite(
        os.path.join(frames_dir, f"frame_{frame_idx:06d}.jpg"),
        cropped
    )

    frame_idx += 1

cap.release()