import cv2
import json
import sys

video_path = sys.argv[1]

cap = cv2.VideoCapture(video_path)
fps = cap.get(cv2.CAP_PROP_FPS) or 30
frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))

prev_gray = None
points = []

sample_every = int(max(1, fps / 2))  # twice per second

while True:
    ret, frame = cap.read()
    if not ret:
        break

    frame_no = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
    if frame_no % sample_every != 0:
        continue

    t = frame_no / fps
    h, w = frame.shape[:2]

    small_w = 320
    small_h = int(small_w * h / w)
    small = cv2.resize(frame, (small_w, small_h))

    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (21, 21), 0)

    if prev_gray is not None:
        diff = cv2.absdiff(prev_gray, gray)
        _, thresh = cv2.threshold(diff, 25, 255, cv2.THRESH_BINARY)

        # Ignore very top/bottom noise
        thresh[: int(small_h * 0.15), :] = 0
        thresh[int(small_h * 0.9) :, :] = 0

        moments = cv2.moments(thresh)

        if moments["m00"] > 1000:
            cx_small = int(moments["m10"] / moments["m00"])
            cx = int(cx_small * w / small_w)
            points.append({"t": round(t, 2), "centerX": cx})

    prev_gray = gray

cap.release()

print(json.dumps({"points": points}))