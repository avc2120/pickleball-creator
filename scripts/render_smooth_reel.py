"""
Render a smooth vertical reel from a source video and motion target points.

Usage:
    python scripts/render_smooth_reel.py <input_video> <points.json> <frames_dir>

This script reads detector points, interpolates a target center and span per frame,
applies a smooth zoom and crop, and writes each rendered frame to <frames_dir>.
"""

import cv2
import json
import os
import sys
import numpy as np

OUT_WIDTH = 1080
OUT_HEIGHT = 1920
SMOOTHING_ALPHA = 0.12
MAX_ZOOM_RATIO = 3.5


def load_motion_points(points_path: str):
    with open(points_path, "r") as f:
        points = json.load(f).get("points", [])
    return points or []


def build_point_series(points, fallback_center_x, fallback_center_y):
    if not points:
        return np.array([]), np.array([]), np.array([]), np.array([])

    times = np.array([p.get("t", 0) for p in points])
    center_xs = np.array([
        p.get("centerX", fallback_center_x)
        if p.get("centerX") is not None
        else fallback_center_x
        for p in points
    ])
    center_ys = np.array([
        p.get("centerY", fallback_center_y)
        if p.get("centerY") is not None
        else fallback_center_y
        for p in points
    ])
    span_widths = np.array([
        p.get("playerSpanWidth", OUT_WIDTH)
        if p.get("playerSpanWidth") is not None
        else OUT_WIDTH
        for p in points
    ])
    span_heights = np.array([
        p.get("playerSpanHeight", OUT_HEIGHT)
        if p.get("playerSpanHeight") is not None
        else OUT_HEIGHT
        for p in points
    ])

    return times, center_xs, center_ys, span_widths, span_heights


def interpolate_target(t, series, fallback):
    times, values = series
    if len(times) <= 1:
        return fallback
    return float(np.interp(t, times, values))


def compute_target_frame_values(
    t,
    times,
    center_xs,
    center_ys,
    span_widths,
    span_heights,
    fallback_center_x,
    fallback_center_y,
):
    if len(times) <= 1:
        return fallback_center_x, fallback_center_y, OUT_WIDTH, OUT_HEIGHT

    target_center_x = interpolate_target(t, (times, center_xs), fallback_center_x)
    target_center_y = interpolate_target(t, (times, center_ys), fallback_center_y)
    target_span_w = interpolate_target(t, (times, span_widths), OUT_WIDTH)
    target_span_h = interpolate_target(t, (times, span_heights), OUT_HEIGHT)

    return target_center_x, target_center_y, target_span_w, target_span_h


def compute_zoom_scale(target_span_w: float, target_span_h: float, baseline_scale: float):
    if target_span_w <= 0 or target_span_h <= 0:
        return baseline_scale

    scale_w = (OUT_WIDTH * 0.95) / target_span_w
    scale_h = (OUT_HEIGHT * 0.85) / target_span_h
    return float(np.clip(min(scale_w, scale_h), baseline_scale, baseline_scale * MAX_ZOOM_RATIO))


def smooth_value(target: float, previous: float | None, alpha: float):
    if previous is None:
        return target
    return alpha * target + (1 - alpha) * previous


def clamp_crop(value: int, max_value: int):
    return max(0, min(max_value, value))


def render_frames(input_path: str, points_path: str, frames_dir: str):
    points = load_motion_points(points_path)

    cap = cv2.VideoCapture(input_path)
    if not cap.isOpened():
        raise RuntimeError(f"Failed to open input video: {input_path}")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    baseline_scale = max(OUT_WIDTH / width, OUT_HEIGHT / height)
    fallback_center_x = (width * baseline_scale) / 2.0
    fallback_center_y = OUT_HEIGHT / 2.0

    times, center_xs, center_ys, span_widths, span_heights = build_point_series(
        points,
        fallback_center_x,
        fallback_center_y,
    )

    os.makedirs(frames_dir, exist_ok=True)

    last_crop_x = None
    last_crop_y = None
    last_scale = None
    frame_idx = 0

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        t = frame_idx / fps
        target_center_x, target_center_y, target_span_w, target_span_h = compute_target_frame_values(
            t,
            times,
            center_xs,
            center_ys,
            span_widths,
            span_heights,
            fallback_center_x,
            fallback_center_y,
        )

        ideal_scale = compute_zoom_scale(target_span_w, target_span_h, baseline_scale)
        scale = smooth_value(ideal_scale, last_scale, SMOOTHING_ALPHA)
        last_scale = scale

        scaled_w = int(np.ceil(width * scale))
        scaled_h = int(np.ceil(height * scale))
        scaled_frame = cv2.resize(frame, (scaled_w, scaled_h))

        source_center_x = target_center_x * scale / baseline_scale
        source_center_y = target_center_y * scale / baseline_scale

        proposed_crop_x = int(source_center_x - OUT_WIDTH / 2)
        proposed_crop_y = int(source_center_y - OUT_HEIGHT / 2)

        crop_x = clamp_crop(proposed_crop_x, scaled_w - OUT_WIDTH)
        crop_y = clamp_crop(proposed_crop_y, scaled_h - OUT_HEIGHT)

        crop_x = int(smooth_value(crop_x, last_crop_x, SMOOTHING_ALPHA))
        crop_y = int(smooth_value(crop_y, last_crop_y, SMOOTHING_ALPHA))

        last_crop_x = crop_x
        last_crop_y = crop_y

        cropped_frame = scaled_frame[crop_y:crop_y + OUT_HEIGHT, crop_x:crop_x + OUT_WIDTH]

        cv2.imwrite(os.path.join(frames_dir, f"frame_{frame_idx:06d}.jpg"), cropped_frame)
        frame_idx += 1

    cap.release()


if __name__ == "__main__":
    render_frames(sys.argv[1], sys.argv[2], sys.argv[3])
