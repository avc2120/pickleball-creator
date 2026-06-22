import cv2
import json
import os
import sys
import math
from ultralytics import YOLO

video_path = sys.argv[1]
debug_output_path = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(video_path)[0] + "-debug.mp4"

model = YOLO("yolo11n.pt")
cap = cv2.VideoCapture(video_path)
fps = cap.get(cv2.CAP_PROP_FPS) or 30
w_frame = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
h_frame = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

sample_every = int(max(1, fps / 5))
points = []

fourcc = cv2.VideoWriter_fourcc(*"mp4v")
out_writer = cv2.VideoWriter(debug_output_path, fourcc, fps / sample_every, (w_frame, h_frame))
if not out_writer.isOpened():
    print(f"ERROR: failed to open debug video writer: {debug_output_path}", file=sys.stderr)
    out_writer = None


def get_label_name(model, cls):
    return str(getattr(model, "names", {}).get(cls, cls)).lower()


def detect_ball_by_color(frame, h):
    blurred = cv2.GaussianBlur(frame, (7, 7), 0)
    hsv = cv2.cvtColor(blurred, cv2.COLOR_BGR2HSV)
    lower = (20, 60, 100)
    upper = (70, 255, 255)
    mask = cv2.inRange(hsv, lower, upper)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel, iterations=1)
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel, iterations=1)
    mask[: int(h * 0.08), :] = 0
    mask[int(h * 0.92) :, :] = 0
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None

    for c in contours:
        area = cv2.contourArea(c)
        if area < 40 or area > 3000:
            continue
        perimeter = cv2.arcLength(c, True)
        if perimeter <= 0:
            continue
        circularity = 4 * math.pi * area / (perimeter * perimeter)
        if circularity < 0.55:
            continue
        (cx, cy), radius = cv2.minEnclosingCircle(c)
        if radius < 3 or radius > 60:
            continue
        x, y, bw, bh = cv2.boundingRect(c)
        ratio = bw / max(bh, 1)
        if ratio < 0.6 or ratio > 1.5:
            continue
        score = circularity * 120 + area / 15
        if best is None or score > best["score"]:
            best = {"cx": int(cx), "cy": int(cy), "score": score}

    return (best["cx"], best["cy"]) if best is not None else None

while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame_no = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
    if frame_no % sample_every != 0:
        continue

    t = frame_no / fps
    if t > 5.0:
        break

    h, w = frame.shape[:2]
    results = model(frame, verbose=False)[0]

    ball_x = None
    ball_y = None
    ball_source = "none"
    best_ball = None

    for box in results.boxes:
        cls = int(box.cls[0])
        conf = float(box.conf[0])
        label = get_label_name(model, cls)
        if conf < 0.2:
            continue

        x1, y1, x2, y2 = box.xyxy[0].tolist()
        bw = x2 - x1
        bh = y2 - y1
        if bw < 8 or bh < 8 or bw > 120 or bh > 120:
            continue

        if cls == 32 or "ball" in label:
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)
            score = conf * (bw * bh)
            if best_ball is None or score > best_ball["score"]:
                best_ball = {"cx": cx, "cy": cy, "box": (int(x1), int(y1), int(x2), int(y2)), "label": label, "conf": conf, "score": score}

    if best_ball is not None:
        ball_x = best_ball["cx"]
        ball_y = best_ball["cy"]
        ball_source = f"yolo({best_ball['label']}:{best_ball['conf']:.2f})"
    else:
        fallback = detect_ball_by_color(frame, h)
        if fallback is not None:
            ball_x, ball_y = fallback
            ball_source = "color-fallback"

    display = frame.copy()
    if ball_x is not None and ball_y is not None:
        # brighter, larger, thicker marker
        cv2.circle(display, (ball_x, ball_y), 28, (0, 255, 255), 4)
        cv2.circle(display, (ball_x, ball_y), 6, (255, 255, 255), -1)
        cv2.putText(display, "BALL", (ball_x + 14, ball_y - 14), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 3, cv2.LINE_AA)
        if best_ball is not None:
            x1, y1, x2, y2 = best_ball["box"]
            cv2.rectangle(display, (x1, y1), (x2, y2), (0, 255, 255), 3)

    cv2.putText(display, f"t={t:.2f} src={ball_source}", (10, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    if out_writer is not None:
        out_writer.write(display)

    print(f"DEBUG frame={frame_no} t={t:.2f} ball_x={ball_x} ball_source={ball_source}", file=sys.stderr)
    points.append({
        "t": round(t, 3),
        "ballX": ball_x,
        "ballY": ball_y,
        "centerX": int(ball_x) if ball_x is not None else None,
        "source": ball_source,
    })

cap.release()
if out_writer is not None:
    out_writer.release()
    print(f"DEBUG closed debug overlay video: {debug_output_path}", file=sys.stderr)

print(json.dumps({"points": points}))
