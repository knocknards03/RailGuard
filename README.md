# RailGuard AI — Abandoned Object Detection System

![Python](https://img.shields.io/badge/Python-3.9%2B-blue?logo=python)
![Flask](https://img.shields.io/badge/Flask-3.0.3-black?logo=flask)
![OpenCV](https://img.shields.io/badge/OpenCV-4.10-green?logo=opencv)
![License](https://img.shields.io/badge/License-MIT-yellow)

> Real-time abandoned baggage detection for railway platforms, powered by OpenCV background subtraction, a centroid-based object tracker, and a simulated Raman spectrometer for chemical threat classification — all surfaced through a live Flask dashboard.

---

## Table of Contents

- [Overview](#overview)
- [Features](#features)
- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [API Reference](#api-reference)
- [Dashboard](#dashboard)
- [Raman Spectrometer Simulation](#raman-spectrometer-simulation)
- [Demo Video Generator](#demo-video-generator)
- [Production Notes](#production-notes)

---

## Overview

RailGuard AI monitors CCTV footage of railway platforms and automatically detects luggage or objects left unattended for an extended period. When an object is flagged, the system:

1. Tracks it across frames using a centroid-based algorithm.
2. Escalates its status from **NORMAL → WARNING → CRITICAL** based on how long it has remained stationary.
3. Triggers a simulated **Raman spectrometer scan** to classify any chemical threat (explosives, narcotics, etc.).
4. Raises an **RPF (Railway Protection Force) alert** with a pre-filled dispatch message.
5. Streams all of this live to a dark-theme operator dashboard over **Server-Sent Events (SSE)**.

The system is pre-configured for *New Delhi Railway Station — Platform 4, CAM-04* but is trivially reconfigurable for any station or camera.

---

## Features

| Feature | Details |
|---|---|
| **Background subtraction** | Frame-differencing + Canny edge detection + morphological closing |
| **Centroid tracker** | Nearest-neighbour matching with configurable disappear timeout |
| **Abandonment timer** | Configurable WARNING (default 10 s demo / 3 min prod) and CRITICAL (30 s / 10 min) thresholds |
| **Raman simulation** | 10-substance library (RDX, TNT, PETN, TATP, AN, Heroin, Cocaine, Meth, Cannabis, Clean) with SNR-based confidence scoring |
| **MJPEG video stream** | Annotated live feed served at `/video_feed` |
| **SSE dashboard** | Real-time stats, tracked objects, alert log, Raman results pushed every second |
| **RPF modal** | One-click acknowledgement + formatted dispatch message |
| **Chart.js analytics** | Activity timeline, Raman scan history bar chart, threat-breakdown donut |
| **Toast + audio alerts** | Web Audio API beep on CRITICAL alerts |
| **Demo asset generator** | Synthetically produces `cut.mp4` + `Frame.png` if assets are missing |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Flask App (app.py)                    │
│  /             → Dashboard HTML                              │
│  /video_feed   → MJPEG stream                                │
│  /stream       → SSE JSON updates (1 Hz)                     │
│  /api/*        → REST endpoints                              │
└────────────────────────┬────────────────────────────────────┘
                         │
              ┌──────────▼──────────┐
              │   DetectionEngine   │  ← background thread
              │  (detection_engine) │
              └──┬──────────────┬───┘
                 │              │
      ┌──────────▼──┐    ┌──────▼──────────┐
      │ ObjectTracker│    │RamanSpectrometer│
      │  (tracker)   │    │(raman_simulator)│
      └──────────────┘    └─────────────────┘
                 │
         ┌───────▼────────┐
         │  EngineState   │  ← thread-safe shared state
         │ (frame, stats, │
         │  alerts, raman)│
         └────────────────┘
```

---

## Project Structure

```
abandoned-object-detection-opencv/
│
├── app.py                   # Flask application — routes, SSE, REST API
├── detection_engine.py      # Core CV pipeline, alert generation, state management
├── tracker.py               # Centroid-based object tracker with abandonment timers
├── raman_simulator.py       # Simulated Raman spectrometer + chemical library
├── generate_demo_video.py   # Synthetic CCTV scene generator (cut.mp4 + Frame.png)
│
├── cut.mp4                  # Demo video (auto-generated if missing)
├── Frame.png                # Reference background frame (auto-generated if missing)
│
├── templates/
│   └── index.html           # Operator dashboard (Jinja2 template)
│
├── static/
│   ├── css/
│   │   └── dashboard.css    # Dark ops-room theme
│   └── js/
│       └── dashboard.js     # SSE client, Chart.js, RPF modal logic
│
└── requirements.txt         # Python dependencies
```

---

## Quick Start

### 1. Prerequisites

- Python 3.9 or higher
- pip

### 2. Clone the repository

```bash
git clone https://github.com/knocknards03/RailGuard.git
cd RailGuard
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run the application

```bash
python app.py
```

The server starts on **http://localhost:5001**.

> If `cut.mp4` or `Frame.png` are missing, the app automatically generates them using `generate_demo_video.py` before starting.

### 5. Open the dashboard

Navigate to **http://localhost:5001** in your browser.

---

## Configuration

All thresholds and paths can be overridden with environment variables — no code changes needed.

| Variable | Default | Description |
|---|---|---|
| `PORT` | `5001` | Flask server port |
| `VIDEO_SRC` | `cut.mp4` | Path to video file or camera index (`0`) |
| `REF_FRAME` | `Frame.png` | Path to clean background reference image |
| `WARN_SECONDS` | `10` | Seconds stationary before WARNING (use `180` for production) |
| `ALERT_SECONDS` | `30` | Seconds stationary before CRITICAL (use `600` for production) |
| `SECRET_KEY` | `railguard-dev-secret` | Flask session secret key |

**Example — use a live camera with production thresholds:**

```bash
VIDEO_SRC=0 WARN_SECONDS=180 ALERT_SECONDS=600 python app.py
```

---

## API Reference

All endpoints return JSON unless noted.

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Operator dashboard (HTML) |
| `GET` | `/video_feed` | MJPEG live video stream |
| `GET` | `/stream` | SSE stream — full dashboard payload every second |
| `GET` | `/api/stats` | Current detection statistics |
| `GET` | `/api/alerts` | All alerts. Supports `?status=CRITICAL` and `?unacknowledged=1` |
| `POST` | `/api/alerts/<id>/acknowledge` | Acknowledge an alert and mark RPF notified |
| `GET` | `/api/raman/history` | Last 20 Raman scan results |
| `POST` | `/api/raman/force_scan` | Force a named-substance scan (body: `{"substance": "RDX"}`) |
| `GET` | `/api/system/status` | Engine uptime, FPS, video source info |

### SSE Payload Schema

```json
{
  "stats": {
    "total_objects": 2,
    "warning_objects": 1,
    "critical_objects": 0,
    "total_alerts": 3,
    "raman_scans": 3,
    "threats_detected": 1,
    "fps": 18.4,
    "uptime_seconds": 142
  },
  "tracked": [
    {
      "id": 0, "x": 362, "y": 290, "w": 30, "h": 22,
      "status": "WARNING", "stationary_secs": 12.3,
      "time_label": "00:12", "confidence": 0.47
    }
  ],
  "alerts": [ { "alert_id": "A1B2C3D4", "status": "WARNING", "..." } ],
  "raman_history": [ { "substance": "Clean", "risk_level": 0, "..." } ],
  "new_alert": false
}
```

---

## Dashboard

The operator dashboard is a single-page app built with vanilla JS, Chart.js, and Font Awesome — no frontend build step required.

### Panels

- **Live Camera Feed** — annotated MJPEG stream with bounding boxes colour-coded by status (green / orange / red). Fullscreen toggle available.
- **Active Tracked Objects** — real-time list of every object currently being tracked, with stationary timer and confidence bar.
- **Raman Spectrometer** — latest scan result card with substance name, risk badge, SNR, detected peaks, and manual scan trigger buttons (RDX, TNT, Heroin, Cocaine, Clear).
- **Alert Log** — filterable list of all raised alerts. Click any alert to open the RPF dispatch modal.
- **Charts** — object activity timeline (30-point rolling), Raman scan history bar, and threat-breakdown donut.

### Bounding Box Colours

| Colour | Status | Condition |
|---|---|---|
| 🟢 Green | NORMAL | Object moving or stationary < warn threshold |
| 🟠 Orange | WARNING | Stationary ≥ `WARN_SECONDS` |
| 🔴 Red | CRITICAL | Stationary ≥ `ALERT_SECONDS` |

---

## Raman Spectrometer Simulation

`raman_simulator.py` simulates a miniaturised portable Raman spectrometer. In a real deployment, replace `RamanSpectrometer.scan()` with your hardware driver (e.g. Wasatch Photonics, Ocean Insight).

### Chemical Library

| Substance | Category | Risk Level |
|---|---|---|
| RDX | EXPLOSIVE | 5 / 5 |
| TNT | EXPLOSIVE | 5 / 5 |
| PETN | EXPLOSIVE | 5 / 5 |
| TATP | EXPLOSIVE | 5 / 5 |
| Ammonium Nitrate | EXPLOSIVE_PRECURSOR | 3 / 5 |
| Heroin | NARCOTIC | 4 / 5 |
| Cocaine | NARCOTIC | 4 / 5 |
| Methamphetamine | NARCOTIC | 4 / 5 |
| Cannabis Resin | NARCOTIC | 2 / 5 |
| Clean | CLEAR | 0 / 5 |

By default, 85% of automatic scans return CLEAR and 15% return a random threat. To always trigger threats for demos, set `THREAT_PROBABILITY = 1.0` in `raman_simulator.py`.

---

## Demo Video Generator

Run `generate_demo_video.py` standalone to regenerate the synthetic test assets:

```bash
python generate_demo_video.py
```

This produces:
- **`cut.mp4`** — 60 seconds of synthetic CCTV footage at 800×480, 20 fps, showing a person walking with luggage, dropping it, and walking away.
- **`Frame.png`** — a clean background reference frame used by the detector.

---

## Production Notes

- **Thresholds**: Set `WARN_SECONDS=180` and `ALERT_SECONDS=600` for real 3-min / 10-min thresholds.
- **Live camera**: Set `VIDEO_SRC=0` (or your camera index / RTSP URL).
- **Reference frame**: Provide a clean background image of the platform as `REF_FRAME`.
- **WSGI server**: Run behind Gunicorn or uWSGI in production. The built-in Flask dev server is single-threaded for SSE.
- **Raman hardware**: Replace `RamanSpectrometer.scan()` in `raman_simulator.py` with your serial/USB driver.
- **Alert routing**: Extend the `acknowledge_alert` endpoint to POST to your RPF communication system.

---

## Requirements

```
flask==3.0.3
opencv-python==4.10.0.84
numpy==1.26.4
```

---

## License

MIT License — see [LICENSE](LICENSE) for details.
