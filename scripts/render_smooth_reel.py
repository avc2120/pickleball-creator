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
baseline_scale = max(out_w / w, out_h / h)

os.makedirs(frames_dir, exist_ok=True)

fallback_center_x = (w * baseline_scale) / 2.0
fallback_center_y = out_h / 2.0
fallback_span_w = out_w
fallback_span_h = out_h

points = points or []

times = np.array([p["t"] for p in points]) if points else np.array([])
center_xs = np.array(
    [
        p.get("centerX", fallback_center_x) if p.get("centerX") is not None else fallback_center_x
        for p in points
    ]
) if points else np.array([])
center_ys = np.array(
    [
        p.get("centerY", fallback_center_y) if p.get("centerY") is not None else fallback_center_y
        for p in points
    ]
) if points else np.array([])
span_widths = np.array(
    [
        p.get("playerSpanWidth", fallback_span_w) if p.get("playerSpanWidth") is not None else fallback_span_w
        for p in points
    ]
) if points else np.array([])
span_heights = np.array(
    [
        p.get("playerSpanHeight", fallback_span_h) if p.get("playerSpanHeight") is not None else fallback_span_h
        for p in points
    ]
) if points else np.array([])

frame_idx = 0
last_crop_x = None
last_crop_y = None
last_scale = None
alpha = 0.12

while True:
    ret, frame = cap.read()
    if not ret:
        break

    t = frame_idx / fps
    if len(points) >= 1:
        target_center_x = np.interp(t, times, center_xs)
        target_center_y = np.interp(t, times, center_ys)
        target_span_w = np.interp(t, times, span_widths)
        target_span_h = np.interp(t, times, span_heights)
    else:
        target_center_x = fallback_center_x
        target_center_y = fallback_center_y
        target_span_w = fallback_span_w
        target_span_h = fallback_span_h

    if target_span_w <= 0 or target_span_h <= 0:
        ideal_scale = baseline_scale
    else:
        scale_w = (out_w * 0.95) / target_span_w
        scale_h = (out_h * 0.85) / target_span_h
        ideal_scale = np.clip(min(scale_w, scale_h), baseline_scale, baseline_scale * 4.5)

    if last_scale is None:
        scale = ideal_scale
    else:
        scale = alpha * ideal_scale + (1 - alpha) * last_scale
    last_scale = scale

    scaled_w = int(np.ceil(w * scale))
    scaled_h = int(np.ceil(h * scale))
    scaled = cv2.resize(frame, (scaled_w, scaled_h))

    source_center_x = target_center_x * scale / baseline_scale
    source_center_y = target_center_y * scale / baseline_scale

    target_crop_x = int(source_center_x - out_w / 2)
    target_crop_y = int(source_center_y - out_h / 2)

    target_crop_x = max(0, min(scaled_w - out_w, target_crop_x))
    target_crop_y = max(0, min(scaled_h - out_h, target_crop_y))

    if last_crop_x is None:
        crop_x = target_crop_x
        crop_y = target_crop_y
    else:
        crop_x = int(alpha * target_crop_x + (1 - alpha) * last_crop_x)
        crop_y = int(alpha * target_crop_y + (1 - alpha) * last_crop_y)

    last_crop_x = crop_x
    last_crop_y = crop_y

    cropped = scaled[crop_y:crop_y + out_h, crop_x:crop_x + out_w]

    cv2.imwrite(
        os.path.join(frames_dir, f"frame_{frame_idx:06d}.jpg"),
        cropped
    )

    frame_idx += 1

cap.release()