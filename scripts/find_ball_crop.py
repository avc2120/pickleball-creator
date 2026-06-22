import cv2
import json
import os
import sys
import math
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


while True:
    ret, frame = cap.read()
    if not ret:
        break

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

    display = frame.copy()
    # draw all players
    for p in players:
        px = p["cx"]
        py = p["cy"]
        x1, y1, x2, y2 = p["box"]
        cv2.rectangle(display, (x1, y1), (x2, y2), (0, 200, 0), 3)
        cv2.circle(display, (px, py), 10, (0, 255, 0), -1)
        cv2.putText(display, "PLAYER", (px + 12, py - 12), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 200, 0), 2, cv2.LINE_AA)

    # mark the average center if available
    if player_center_x is not None:
        cv2.line(display, (player_center_x, 0), (player_center_x, h), (0, 255, 255), 3)
        cv2.circle(display, (player_center_x, player_center_y), 15, (255, 0, 255), 3)
        cv2.putText(display, "CENTER", (player_center_x + 10, player_center_y - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 0, 255), 3, cv2.LINE_AA)

    cv2.putText(display, f"t={t:.2f} src=players", (10, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

    if out_writer is not None:
        out_writer.write(display)

    print(f"DEBUG frame={frame_no} t={t:.2f} players={len(players)} centerX={player_center_x} centerY={player_center_y}", file=sys.stderr)
    # compute scaled coordinates relative to a 1920px height frame (what ffmpeg will scale to)
    scaled_width = int(round(w * (1920.0 / h)))
    scaled_center_x = int(round(player_center_x * (1920.0 / h))) if player_center_x is not None else None
    scaled_center_y = int(round(player_center_y * (1920.0 / h))) if player_center_y is not None else None

    points.append({
        "t": round(t, 3),
        "centerX": scaled_center_x,
        "centerY": scaled_center_y,
        "scaledWidth": scaled_width,
        "players": [{"cx": p["cx"], "cy": p["cy"]} for p in players],
        "source": "yolo-players",
    })

cap.release()
if out_writer is not None:
    out_writer.release()
    print(f"DEBUG closed debug overlay video: {debug_output_path}", file=sys.stderr)

print(json.dumps({"points": points}))
