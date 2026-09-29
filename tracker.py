"""
RailGuard - Object Tracker
Tracks objects across video frames with time-based abandonment detection.
Threshold: object stationary for 3-10 minutes triggers an alert.
"""

import math
import os
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple


# ── Abandonment thresholds ────────────────────────────────────────────────────
# DEMO mode: 10s → WARNING, 30s → CRITICAL  (fast enough to see in a demo)
# PRODUCTION: change to 180 and 600 (3 min / 10 min) for real deployment
ABANDON_WARN_SECONDS  = int(os.environ.get("WARN_SECONDS",  "10"))
ABANDON_ALERT_SECONDS = int(os.environ.get("ALERT_SECONDS", "30"))
STATIONARY_PIXEL_TOL  = 8     # pixels of movement still considered "stationary"
MAX_DISAPPEAR_FRAMES  = 30    # frames before an object is dropped


@dataclass
class TrackedObject:
    obj_id:       int
    x:            int
    y:            int
    w:            int
    h:            int
    cx:           float
    cy:           float
    first_seen:   float = field(default_factory=time.time)
    last_seen:    float = field(default_factory=time.time)
    stationary_since: Optional[float] = None  # epoch when it stopped moving
    disappeared:  int   = 0
    confidence:   float = 0.0  # 0-1 abandonment confidence

    # ── derived ──────────────────────────────────────────────────────────────
    @property
    def stationary_seconds(self) -> float:
        if self.stationary_since is None:
            return 0.0
        return time.time() - self.stationary_since

    @property
    def status(self) -> str:
        """NORMAL / WARNING / CRITICAL"""
        s = self.stationary_seconds
        if s >= ABANDON_ALERT_SECONDS:
            return "CRITICAL"
        if s >= ABANDON_WARN_SECONDS:
            return "WARNING"
        return "NORMAL"

    @property
    def time_label(self) -> str:
        s = int(self.stationary_seconds)
        m, sec = divmod(s, 60)
        return f"{m:02d}:{sec:02d}"

    def update_confidence(self):
        """Linearly ramp confidence from 0 → 1 between warn and alert thresholds."""
        s = self.stationary_seconds
        if s < ABANDON_WARN_SECONDS:
            self.confidence = round(s / ABANDON_WARN_SECONDS * 0.4, 3)   # 0–0.4 in warmup
        elif s < ABANDON_ALERT_SECONDS:
            ratio = (s - ABANDON_WARN_SECONDS) / (ABANDON_ALERT_SECONDS - ABANDON_WARN_SECONDS)
            self.confidence = round(0.4 + ratio * 0.6, 3)                 # 0.4–1.0
        else:
            self.confidence = 1.0


class ObjectTracker:
    def __init__(self):
        self.objects: Dict[int, TrackedObject] = {}
        self._id_count = 0

    # ── public ───────────────────────────────────────────────────────────────

    def update(self, detections: List[List[int]]) -> Tuple[List, List[TrackedObject]]:
        """
        Parameters
        ----------
        detections : list of [x, y, w, h]

        Returns
        -------
        tracked_objects : list of TrackedObject (all currently tracked)
        abandoned       : list of TrackedObject whose status is WARNING or CRITICAL
        """
        now = time.time()
        matched_ids = set()

        for (x, y, w, h) in detections:
            cx = x + w / 2
            cy = y + h / 2
            best_id, best_dist = self._nearest(cx, cy)

            if best_id is not None and best_dist < 40:
                obj = self.objects[best_id]
                moved = math.hypot(cx - obj.cx, cy - obj.cy)

                # Update bounding box & centre
                obj.x, obj.y, obj.w, obj.h = x, y, w, h
                obj.cx, obj.cy = cx, cy
                obj.last_seen  = now
                obj.disappeared = 0

                # Decide whether it has moved
                if moved <= STATIONARY_PIXEL_TOL:
                    if obj.stationary_since is None:
                        obj.stationary_since = now
                else:
                    obj.stationary_since = None  # reset timer — object moved

                obj.update_confidence()
                matched_ids.add(best_id)
            else:
                # New object
                obj = TrackedObject(
                    obj_id=self._id_count,
                    x=x, y=y, w=w, h=h,
                    cx=cx, cy=cy,
                    stationary_since=now,
                )
                self.objects[self._id_count] = obj
                matched_ids.add(self._id_count)
                self._id_count += 1

        # Age out disappeared objects
        for oid in list(self.objects.keys()):
            if oid not in matched_ids:
                self.objects[oid].disappeared += 1
                if self.objects[oid].disappeared > MAX_DISAPPEAR_FRAMES:
                    del self.objects[oid]

        tracked   = list(self.objects.values())
        abandoned = [o for o in tracked if o.status in ("WARNING", "CRITICAL")]
        return tracked, abandoned

    def get_all(self) -> List[TrackedObject]:
        return list(self.objects.values())

    def reset(self):
        self.objects.clear()
        self._id_count = 0

    # ── private ──────────────────────────────────────────────────────────────

    def _nearest(self, cx: float, cy: float):
        best_id, best_dist = None, float("inf")
        for oid, obj in self.objects.items():
            d = math.hypot(cx - obj.cx, cy - obj.cy)
            if d < best_dist:
                best_dist = d
                best_id   = oid
        return best_id, best_dist
