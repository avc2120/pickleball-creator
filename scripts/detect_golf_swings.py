import cv2
import json
import sys
import numpy as np


def smooth(values, window=5):
    if len(values) < window:
        return values

    kernel = np.ones(window) / window
    return np.convolve(values, kernel, mode="same")


def merge_close_clips(clips, min_gap=2.0):
    if not clips:
        return []

    merged = [clips[0]]

    for clip in clips[1:]:
        prev = merged[-1]

        if clip["start"] - prev["end"] <= min_gap:
            prev["end"] = max(prev["end"], clip["end"])
        else:
            merged.append(clip)

    return merged


def detect_golf_swings(video_path):
    cap = cv2.VideoCapture(video_path)

    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    sample_fps = 10
    sample_every = max(1, int(fps / sample_fps))

    prev_gray = None
    motion_scores = []
    timestamps = []

    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        if frame_idx % sample_every == 0:
            small = cv2.resize(frame, (320, 180))
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            gray = cv2.GaussianBlur(gray, (5, 5), 0)

            if prev_gray is not None:
                diff = cv2.absdiff(gray, prev_gray)
                score = float(np.mean(diff))

                motion_scores.append(score)
                timestamps.append(frame_idx / fps)

            prev_gray = gray

        frame_idx += 1

    cap.release()

    if not motion_scores:
        return []

    scores = np.array(smooth(motion_scores, window=5))

    mean = float(np.mean(scores))
    std = float(np.std(scores))

    # Tune this number later.
    threshold = mean + std * 1.0

    clips = []

    threshold = float(np.percentile(scores, 90))
    peak_indices = np.where(scores > threshold)[0]

    if len(peak_indices) > 0:
        groups = []
        current = [peak_indices[0]]

        for idx in peak_indices[1:]:
            prev = current[-1]

            # Group peaks close together into one swing candidate
            if timestamps[idx] - timestamps[prev] <= 1.0:
                current.append(idx)
            else:
                groups.append(current)
                current = [idx]

        groups.append(current)

        last_peak_time = -999

        for group in groups:
            # Pick strongest motion point in this group
            peak_idx = max(group, key=lambda idx: scores[idx])
            peak_time = timestamps[peak_idx]

            # Prevent duplicate clips from one swing
            if peak_time - last_peak_time < 3.0:
                continue

            start_time = max(0, peak_time - 1.5)
            end_time = peak_time + 2.0

            clips.append({
                "start": round(start_time, 2),
                "end": round(end_time, 2),
                "label": "golf_swing"
            })

            last_peak_time = peak_time

    return clips


if __name__ == "__main__":
    input_video = sys.argv[1]

    clips = detect_golf_swings(input_video)

    print(json.dumps({"clips": clips}))