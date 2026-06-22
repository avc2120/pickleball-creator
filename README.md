# Pickleball Creator

Automatically convert horizontal pickleball videos into Instagram-ready vertical highlights using AI-powered player tracking, smart camera panning, and dynamic reframing.

## Features

### Automatic Vertical Reframing

Converts 16:9 pickleball videos into 9:16 vertical videos suitable for:

* Instagram Reels
* TikTok
* YouTube Shorts

### AI Player Detection

Uses YOLOv8 to detect players on the court and estimate the center of the rally.

### Smart Camera Movement

Instead of a fixed crop, the virtual camera:

* Tracks player positions
* Computes rally center
* Smoothly pans across the court
* Avoids abrupt camera jumps

### Motion-Aware Framing

Motion detection is combined with player detection to better capture action during:

* Fast exchanges
* Wide dinks
* ATP attempts
* Ernes
* Player movement across the court

### Debug Visualization

Generate an optional debug video showing:

* Detected players
* Rally center
* Motion center
* Camera target

---

## How It Works

### Detection Pipeline

```text
Input Video
    ↓
YOLOv8 Player Detection
    ↓
Motion Detection
    ↓
Interest Center Calculation
    ↓
Camera Path Generation
    ↓
Vertical Reel Rendering
    ↓
Output Video
```

### Interest Center

The camera does not follow the ball directly.

Instead, it computes an "interest center" based on:

```text
80% Player Center
20% Motion Center
```

This produces smoother and more watchable camera movement.

---

## Tech Stack

### Frontend

* Next.js
* React
* TypeScript

### Backend

* Next.js API Routes
* Node.js

### Computer Vision

* Python
* OpenCV
* Ultralytics YOLOv8

### Video Processing

* FFmpeg

---

## Local Development

### Prerequisites

Install:

* Node.js 20+
* Python 3.11+
* FFmpeg

Verify FFmpeg:

```bash
ffmpeg -version
```

---

### Install Dependencies

#### Frontend

```bash
npm install
```

#### Python Environment

```bash
python3 -m venv yolo-env
source yolo-env/bin/activate

pip install ultralytics opencv-python numpy
```

---

### Run Locally

```bash
npm run dev
```

Open:

```text
http://localhost:3000
```

Upload a pickleball video and generate a vertical version automatically.

---

## Project Structure

```text
pickleball-creator/

├── src/
│   ├── app/
│   │   └── api/
│   │       └── process-video/
│   │           └── route.ts
│
├── scripts/
│   ├── find_ball_crop.py
│   ├── render_smooth_reel.py
│
├── yolo-env/
│
├── public/
│
└── README.md
```

---

## Current Roadmap

### Completed

* Upload video
* Player detection
* Rally center estimation
* Motion-aware camera targeting
* Smooth virtual camera panning
* Vertical reel export

### In Progress

* Dynamic zoom
* Better rally detection
* Highlight ranking
* Multi-player tracking with ByteTrack

### Future

* Automatic highlight generation
* Point detection
* Celebration detection
* AI-generated captions
* Social media publishing workflow

---

## Example Use Cases

* Turn full pickleball games into vertical content
* Create Instagram Reels automatically
* Generate highlight clips for tournaments
* Produce social-ready content without manual editing

---

## License

MIT

