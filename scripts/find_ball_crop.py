import cv2
import json
import os
import sys
import math
from ultralytics import YOLO

SAMPLE_EVERY = 5  # sample every 5 frames for smoother tracking and lower overhead
TARGET_HEIGHT = 1920.0


def get_label_name(model, cls):
    return str(getattr(model, "names", {}).get(cls, cls)).lower()


def is_player_box(cls: int, label: str, conf: float, width: float, height: float) -> bool:
    if conf < 0.2:
        return False
    if width < 20 or height < 40:
        return False
    return cls == 0 or "person" in label


def collect_players(results, model):
    players = []
    for box in results.boxes:
        cls = int(box.cls[0])
        conf = float(box.conf[0])
        label = get_label_name(model, cls)

        print(
            f"YOLO DETECTED: {model.names.get(cls, cls)} conf={conf:.2f}",
            file=sys.stderr,
        )

        x1, y1, x2, y2 = box.xyxy[0].tolist()
        bw = x2 - x1
        bh = y2 - y1

        if not is_player_box(cls, label, conf, bw, bh):
            continue

        cx = int((x1 + x2) / 2)
        cy = int((y1 + y2) / 2)
        players.append(
            {
                "cx": cx,
                "cy": cy,
                "box": (int(x1), int(y1), int(x2), int(y2)),
                "conf": conf,
            }
        )

    return players


def detect_motion_center(frame, prev_gray):
    h = frame.shape[0]
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (21, 21), 0)

    if prev_gray is None:
        return None, 0, gray

    diff = cv2.absdiff(prev_gray, gray)
    _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)

    thresh[: int(h * 0.12), :] = 0
    thresh[int(h * 0.92) :, :] = 0

    moments = cv2.moments(thresh)
    motion_strength = int(moments.get("m00", 0))
    if motion_strength <= 5000:
        return None, motion_strength, gray

    motion_center_x = int(moments["m10"] / moments["m00"])
    return motion_center_x, motion_strength, gray


def scale_value(value, frame_height):
    return int(round(value * TARGET_HEIGHT / frame_height))


def compute_player_stats(players):
    xs = [p["cx"] for p in players]
    ys = [p["cy"] for p in players]
    left, right = min(xs), max(xs)
    top, bottom = min(ys), max(ys)

    return {
        "center_x": round((left + right) / 2),
        "center_y": round((top + bottom) / 2),
        "span_width": right - left,
        "span_height": bottom - top,
    }


def make_point_entry(
    t,
    player_stats,
    motion_center_x,
    motion_strength,
    frame_height,
    player_count,
    scaled_width,
):
    if player_stats is None:
        return {
            "t": round(t, 3),
            "centerX": None,
            "centerY": None,
            "playerCenterX": None,
            "playerCenterY": None,
            "motionCenterX": None,
            "motionStrength": motion_strength,
            "playerSpanWidth": None,
            "playerSpanHeight": None,
            "playerCount": player_count,
            "scaledWidth": scaled_width,
            "source": "yolo-players-motion",
        }

    if motion_center_x is not None:
        interest_x = int(0.8 * player_stats["center_x"] + 0.2 * motion_center_x)
    else:
        interest_x = player_stats["center_x"]

    return {
        "t": round(t, 3),
        "centerX": scale_value(interest_x, frame_height),
        "centerY": scale_value(player_stats["center_y"], frame_height),
        "playerCenterX": scale_value(player_stats["center_x"], frame_height),
        "playerCenterY": scale_value(player_stats["center_y"], frame_height),
        "motionCenterX": scale_value(motion_center_x, frame_height)
        if motion_center_x is not None
        else None,
        "motionStrength": motion_strength,
        "playerSpanWidth": scale_value(player_stats["span_width"], frame_height),
        "playerSpanHeight": scale_value(player_stats["span_height"], frame_height),
        "playerCount": player_count,
        "scaledWidth": scaled_width,
        "source": "yolo-players-motion",
    }


def main():
    video_path = sys.argv[1]
    debug_output_path = (
        sys.argv[2]
        if len(sys.argv) > 2
        else os.path.splitext(video_path)[0] + "-debug.mp4"
    )

    model = YOLO("yolov8s.pt")
    cap = cv2.VideoCapture(video_path)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    w_frame = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    h_frame = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    out_writer = cv2.VideoWriter(
        debug_output_path,
        fourcc,
        fps / SAMPLE_EVERY,
        (w_frame, h_frame),
    )

    if not out_writer.isOpened():
        print(
            f"ERROR: failed to open debug video writer: {debug_output_path}",
            file=sys.stderr,
        )
        out_writer = None

    points = []
    prev_gray = None

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        motion_center_x, motion_strength, prev_gray = detect_motion_center(frame, prev_gray)
        frame_no = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
        if frame_no % SAMPLE_EVERY != 0:
            continue

        t = frame_no / fps
        h, w = frame.shape[:2]
        results = model(frame, verbose=False)[0]
        players = collect_players(results, model)
        player_stats = compute_player_stats(players) if players else None

        if player_stats:
            print(
                f"DEBUG frame={frame_no} t={t:.2f} players={len(players)} "
                f"centerX={player_stats['center_x']} centerY={player_stats['center_y']}",
                file=sys.stderr,
            )
        else:
            print(
                f"DEBUG frame={frame_no} t={t:.2f} players=0 centerX=None centerY=None",
                file=sys.stderr,
            )

        scaled_width = int(round(w * (TARGET_HEIGHT / h)))
        points.append(
            make_point_entry(
                t,
                player_stats,
                motion_center_x,
                motion_strength,
                h,
                len(players),
                scaled_width,
            )
        )

        if out_writer is not None:
            out_writer.write(frame)

    cap.release()
    if out_writer is not None:
        out_writer.release()
        print(
            f"DEBUG closed debug overlay video: {debug_output_path}",
            file=sys.stderr,
        )

    print(json.dumps({"points": points}))


if __name__ == "__main__":
    main()


