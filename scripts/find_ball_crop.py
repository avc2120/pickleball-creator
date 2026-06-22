import cv2
import json
import os
import sys
import math
import numpy as np
from ultralytics import YOLO

video_path = sys.argv[1]
debug_output_path = sys.argv[2] if len(sys.argv) > 2 else os.path.splitext(video_path)[0] + "-debug.mp4"

model = YOLO("yolov8s.pt")
cap = cv2.VideoCapture(video_path)
fps = cap.get(cv2.CAP_PROP_FPS) or 30
w_frame = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
h_frame = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

sample_every = 5  # 2 samples per second for smoother tracking (less detection overhead)
points = []

fourcc = cv2.VideoWriter_fourcc(*"mp4v")
out_writer = cv2.VideoWriter(debug_output_path, fourcc, fps / sample_every, (w_frame, h_frame))
if not out_writer.isOpened():
    print(f"ERROR: failed to open debug video writer: {debug_output_path}", file=sys.stderr)
    out_writer = None


def get_label_name(model, cls):
    return str(getattr(model, "names", {}).get(cls, cls)).lower()

def detect_motion_center(frame, prev_gray):
    h, w = frame.shape[:2]

    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (21, 21), 0)

    if prev_gray is None:
        return None, 0, gray

    diff = cv2.absdiff(prev_gray, gray)
    _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)

    # Ignore noisy regions
    thresh[: int(h * 0.12), :] = 0
    thresh[int(h * 0.92) :, :] = 0

    moments = cv2.moments(thresh)

    if moments["m00"] <= 5000:
        return None, int(moments["m00"]), gray

    motion_center_x = int(moments["m10"] / moments["m00"])
    motion_strength = int(moments["m00"])

    return motion_center_x, motion_strength, gray

prev_gray = None
while True:
    ret, frame = cap.read()
    if not ret:
        break

    motion_center_x, motion_strength, prev_gray = detect_motion_center(
        frame,
        prev_gray
    )
    
    frame_no = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
    if frame_no % sample_every != 0:
        continue

    t = frame_no / fps

    h, w = frame.shape[:2]
    results = model(frame, verbose=False)[0]

    # PLAYER detection: collect all person boxes and compute average X
    players: list[dict] = []
    for box in results.boxes:
        cls = int(box.cls[0])
        conf = float(box.conf[0])
        label = get_label_name(model, cls)

        # print detected class for debugging
        print(f"YOLO DETECTED: {model.names.get(cls, cls)} conf={conf:.2f}", file=sys.stderr)

        if conf < 0.2:
            continue

        x1, y1, x2, y2 = box.xyxy[0].tolist()
        bw = x2 - x1
        bh = y2 - y1

        # size filter to ignore tiny/huge boxes
        if bw < 20 or bh < 40:
            continue

        if cls == 0 or "person" in label:
            cx = int((x1 + x2) / 2)
            cy = int((y1 + y2) / 2)
            players.append({"cx": cx, "cy": cy, "box": (int(x1), int(y1), int(x2), int(y2)), "conf": conf})

    # compute average player center X if we have players
    player_center_x = None
    player_center_y = None
    if players:
        # compute bounding box encompassing all players
        xs = [p["cx"] for p in players]
        ys = [p["cy"] for p in players]
        left = min(xs)
        right = max(xs)
        top = min(ys)
        bottom = max(ys)
        # center of the bounding box
        player_center_x = round((left + right) / 2)
        player_center_y = round((top + bottom) / 2)

    print(f"DEBUG frame={frame_no} t={t:.2f} players={len(players)} centerX={player_center_x} centerY={player_center_y}", file=sys.stderr)
    # compute scaled coordinates relative to a 1920px height frame (what ffmpeg will scale to)
    scaled_width = int(round(w * (1920.0 / h)))
    scale_factor = 1920.0 / h

    if player_center_x is not None:
        if motion_center_x is not None:
            interest_center_x = int(0.8 * player_center_x + 0.2 * motion_center_x)
        else:
            interest_center_x = player_center_x

        scaled_center_x = int(round(interest_center_x * scale_factor))
        scaled_center_y = int(round(player_center_y * scale_factor))
        scaled_motion_center_x = (
            int(round(motion_center_x * scale_factor))
            if motion_center_x is not None
            else None
        )
    else:
        interest_center_x = None
        scaled_center_x = None
        scaled_center_y = None
        scaled_motion_center_x = None

    scaled_player_span_width = (
        int(round((right - left) * (1920.0 / h)))
        if player_center_x is not None
        else None
    )
    scaled_player_span_height = (
        int(round((bottom - top) * (1920.0 / h)))
        if player_center_x is not None
        else None
    )

    scaled_player_center_x = int(round(player_center_x * scale_factor))
    scaled_player_center_y = int(round(player_center_y * scale_factor))

    scaled_interest_center_x = int(round(interest_center_x * scale_factor))
    scaled_interest_center_y = scaled_player_center_y

    points.append({
        "t": round(t, 3), # final camera target
        "centerX": scaled_interest_center_x,
        "centerY": scaled_player_center_y,

        # raw inputs
        "playerCenterX": scaled_player_center_x,
        "playerCenterY": scaled_player_center_y,

        "motionCenterX": scaled_motion_center_x,
        "motionStrength": motion_strength,

        # zoom inputs
        "playerSpanWidth": scaled_player_span_width,
        "playerSpanHeight": scaled_player_span_height,

        # debugging
        "playerCount": len(players),
        "scaledWidth": scaled_width,

        "source": "yolo-players-motion"
    })

cap.release()
if out_writer is not None:
    out_writer.release()
    print(f"DEBUG closed debug overlay video: {debug_output_path}", file=sys.stderr)

print(json.dumps({"points": points}))


