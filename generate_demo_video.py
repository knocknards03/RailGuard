"""
RailGuard - Demo Video Generator
Creates cut.mp4 and Frame.png synthetically using OpenCV.
Simulates a railway platform scene with:
  - Static background (platform floor, benches, pillars)
  - A person walking with luggage, then leaving it behind
  - A second stationary bag that never moves (immediate suspect)
  - Some background noise / crowd movement
Run once:  python3 generate_demo_video.py
"""

import cv2
import numpy as np
import os

BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
VIDEO_OUT  = os.path.join(BASE_DIR, "cut.mp4")
FRAME_OUT  = os.path.join(BASE_DIR, "Frame.png")

WIDTH, HEIGHT = 800, 480
FPS           = 20
DURATION_SEC  = 60          # 60 seconds of footage
TOTAL_FRAMES  = FPS * DURATION_SEC


# ── Colour palette ────────────────────────────────────────────────────────────
C_FLOOR      = (60,  55,  50)    # dark concrete
C_PLATFORM   = (80,  75,  70)
C_BENCH      = (100, 90,  80)
C_PILLAR     = (90,  85,  78)
C_YELLOW_LINE= (0,  200, 220)    # safety line
C_BAG1       = (30,  60, 120)    # blue backpack
C_BAG2       = (20, 100,  40)    # green suitcase
C_PERSON     = (180,130, 100)    # skin tone placeholder
C_TEXT       = (220, 220, 220)


def draw_background(frame: np.ndarray):
    """Draw static platform background."""
    frame[:] = C_FLOOR

    # Platform surface
    cv2.rectangle(frame, (0, 200), (WIDTH, HEIGHT), C_PLATFORM, -1)

    # Yellow safety line
    cv2.line(frame, (0, 210), (WIDTH, 210), C_YELLOW_LINE, 3)

    # Pillars
    for px in [120, 320, 520, 700]:
        cv2.rectangle(frame, (px, 0), (px + 22, 200), C_PILLAR, -1)
        cv2.rectangle(frame, (px, 0), (px + 22, 200), (110,105,95), 2)

    # Benches
    for bx in [150, 420]:
        cv2.rectangle(frame, (bx, 280), (bx + 100, 310), C_BENCH, -1)
        cv2.rectangle(frame, (bx + 5, 310), (bx + 15, 340), C_BENCH, -1)
        cv2.rectangle(frame, (bx + 85, 310), (bx + 95, 340), C_BENCH, -1)

    # Overhead signage strip
    cv2.rectangle(frame, (0, 0), (WIDTH, 30), (40, 40, 45), -1)
    cv2.putText(frame, "NEW DELHI RAILWAY STATION  |  PLATFORM 4  |  CAM-04",
                (10, 20), cv2.FONT_HERSHEY_SIMPLEX, 0.45, C_TEXT, 1)

    # Track hint at bottom
    cv2.rectangle(frame, (0, 440), (WIDTH, HEIGHT), (35, 33, 30), -1)
    cv2.line(frame, (0, 442), (WIDTH, 442), (80, 75, 70), 2)


def draw_bag(frame, x, y, w, h, color, label="BAG"):
    """Draw a luggage rectangle with a handle."""
    cv2.rectangle(frame, (x, y), (x + w, y + h), color, -1)
    cv2.rectangle(frame, (x, y), (x + w, y + h), tuple(max(0, c - 40) for c in color), 2)
    # Handle
    hx = x + w // 2 - 6
    cv2.rectangle(frame, (hx, y - 8), (hx + 12, y), tuple(max(0, c - 60) for c in color), 2)
    cv2.putText(frame, label, (x + 2, y + h - 4),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, (220, 220, 220), 1)


def draw_person(frame, x, y, direction=1):
    """Simple stick-figure person."""
    # Body
    cv2.rectangle(frame, (x, y + 20), (x + 20, y + 55), C_PERSON, -1)
    # Head
    cv2.circle(frame, (x + 10, y + 12), 12, C_PERSON, -1)
    # Legs (animated suggestion)
    cv2.line(frame, (x + 5,  y + 55), (x,       y + 80), C_PERSON, 3)
    cv2.line(frame, (x + 15, y + 55), (x + 20 + direction * 5, y + 80), C_PERSON, 3)


def add_noise(frame, intensity=4):
    """Add subtle sensor noise to look like real CCTV."""
    noise = np.random.randint(-intensity, intensity, frame.shape, dtype=np.int16)
    frame = np.clip(frame.astype(np.int16) + noise, 0, 255).astype(np.uint8)
    return frame


def generate():
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(VIDEO_OUT, fourcc, FPS, (WIDTH, HEIGHT))

    print(f"Generating {TOTAL_FRAMES} frames ({DURATION_SEC}s @ {FPS}fps)…")

    # ── Object trajectories ───────────────────────────────────────────────────
    # Person 1: walks from left → right carrying bag1, drops it at frame 200, walks away
    # Bag 2:    stationary suitcase near bench from frame 0 (already abandoned)
    # Person 2: crosses frame 300–450 (background crowd)

    BAG2_X, BAG2_Y = 440, 290     # stationary green suitcase near bench

    first_frame_saved = False

    for f in range(TOTAL_FRAMES):
        frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
        draw_background(frame)

        t = f / FPS   # time in seconds

        # ── Bag 2: always present, stationary ────────────────────────────────
        draw_bag(frame, BAG2_X, BAG2_Y, 38, 28, C_BAG2, "SUIT")

        # ── Person 1 + Bag 1 ─────────────────────────────────────────────────
        if f < 200:
            # Person walking right with bag
            px = 40 + int(f * 1.8)
            py = 270
            draw_person(frame, px, py, direction=1)
            draw_bag(frame, px + 22, py + 20, 30, 22, C_BAG1, "BAG")
        elif f < 280:
            # Person puts down bag and walks away (bag stays)
            px = 40 + int(200 * 1.8)
            bag_x = px + 22
            draw_bag(frame, bag_x, 290, 30, 22, C_BAG1, "BAG")
            # Person walks right without bag
            px2 = px + int((f - 200) * 2.5)
            if px2 < WIDTH - 30:
                draw_person(frame, px2, 270, direction=1)
        else:
            # Person gone, bag remains
            bag_x = 40 + int(200 * 1.8) + 22
            draw_bag(frame, bag_x, 290, 30, 22, C_BAG1, "BAG")

        # ── Person 2: background passerby ────────────────────────────────────
        if 300 <= f <= 450:
            px2 = WIDTH - int((f - 300) * 3.5)
            if 0 < px2 < WIDTH:
                draw_person(frame, px2, 310, direction=-1)

        # ── Timestamp overlay ─────────────────────────────────────────────────
        ts = f"FRAME {f:04d}  |  T+{t:.1f}s"
        cv2.putText(frame, ts, (10, HEIGHT - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.38, (160, 160, 160), 1)

        # ── Noise ────────────────────────────────────────────────────────────
        frame = add_noise(frame, intensity=3)

        # Save first frame as reference
        if not first_frame_saved:
            clean = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
            draw_background(clean)
            cv2.imwrite(FRAME_OUT, clean)
            first_frame_saved = True
            print(f"  Saved reference frame → {FRAME_OUT}")

        writer.write(frame)

        if f % (FPS * 10) == 0:
            print(f"  {f}/{TOTAL_FRAMES} frames written…")

    writer.release()
    print(f"  Saved video          → {VIDEO_OUT}")
    print("Done. Both assets are ready.")


if __name__ == "__main__":
    generate()
