"""
RailGuard - Detection Engine
Orchestrates video frame analysis, abandoned-object tracking, Raman spectroscopy
integration and threat classification. Feeds the Flask dashboard via shared state.
"""

import cv2
import numpy as np
import threading
import time
import uuid
import logging
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

from tracker import ObjectTracker, TrackedObject, ABANDON_WARN_SECONDS
from raman_simulator import RamanSpectrometer, RamanScanResult

log = logging.getLogger("detection_engine")
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")


# ── Alert record ─────────────────────────────────────────────────────────────

@dataclass
class ThreatAlert:
    alert_id:      str
    object_id:     int
    status:        str          # WARNING / CRITICAL
    location:      str          # e.g. "Platform 4 – Coach B3"
    camera_id:     str
    station:       str
    bbox:          List[int]    # [x, y, w, h]
    confidence:    float        # overall threat confidence 0-1
    raman:         Optional[dict]  # RamanScanResult.to_dict() or None
    timestamp:     float = field(default_factory=time.time)
    acknowledged:  bool  = False
    rpf_notified:  bool  = False

    def to_dict(self) -> dict:
        d = asdict(self)
        d["time_str"] = time.strftime("%H:%M:%S", time.localtime(self.timestamp))
        d["date_str"] = time.strftime("%d %b %Y",  time.localtime(self.timestamp))
        return d


# ── Shared engine state (thread-safe) ────────────────────────────────────────

class EngineState:
    def __init__(self):
        self._lock         = threading.Lock()
        self.alerts:       List[ThreatAlert]        = []
        self.tracked:      List[dict]               = []
        self.frame_bytes:  Optional[bytes]          = None
        self.stats         = {
            "total_objects":    0,
            "warning_objects":  0,
            "critical_objects": 0,
            "total_alerts":     0,
            "raman_scans":      0,
            "threats_detected": 0,
            "fps":              0.0,
            "uptime_seconds":   0,
            "last_alert_time":  None,
        }
        self.raman_history: List[dict] = []   # last 50 scan results
        self._start_time = time.time()

    # ── thread-safe getters ──────────────────────────────────────────────────

    def get_frame(self) -> Optional[bytes]:
        with self._lock:
            return self.frame_bytes

    def get_dashboard_payload(self) -> dict:
        with self._lock:
            return {
                "stats":         dict(self.stats),
                "tracked":       list(self.tracked),
                "alerts":        [a.to_dict() for a in self.alerts[-50:]],
                "raman_history": list(self.raman_history[-20:]),
            }

    def get_alerts(self) -> List[dict]:
        with self._lock:
            return [a.to_dict() for a in self.alerts]

    def acknowledge_alert(self, alert_id: str) -> bool:
        with self._lock:
            for a in self.alerts:
                if a.alert_id == alert_id:
                    a.acknowledged = True
                    a.rpf_notified = True
                    return True
        return False

    # ── thread-safe setters ──────────────────────────────────────────────────

    def update(
        self,
        frame_bytes: bytes,
        tracked: List[TrackedObject],
        abandoned: List[TrackedObject],
        new_alerts: List[ThreatAlert],
        fps: float,
        raman_results: List[RamanScanResult],
    ):
        with self._lock:
            self.frame_bytes = frame_bytes
            self.tracked = [self._obj_to_dict(o) for o in tracked]

            for alert in new_alerts:
                self.alerts.append(alert)

            for r in raman_results:
                self.raman_history.append(r.to_dict())

            self.stats.update({
                "total_objects":    len(tracked),
                "warning_objects":  sum(1 for o in tracked if o.status == "WARNING"),
                "critical_objects": sum(1 for o in tracked if o.status == "CRITICAL"),
                "total_alerts":     len(self.alerts),
                "raman_scans":      self.stats["raman_scans"] + len(raman_results),
                "threats_detected": self.stats["threats_detected"]
                                    + sum(1 for r in raman_results if r.is_threat),
                "fps":              round(fps, 1),
                "uptime_seconds":   int(time.time() - self._start_time),
                "last_alert_time":  (
                    time.strftime("%H:%M:%S")
                    if new_alerts else self.stats["last_alert_time"]
                ),
            })

    @staticmethod
    def _obj_to_dict(o: TrackedObject) -> dict:
        return {
            "id":               o.obj_id,
            "x": o.x, "y": o.y, "w": o.w, "h": o.h,
            "cx": o.cx, "cy": o.cy,
            "status":           o.status,
            "stationary_secs":  round(o.stationary_seconds, 1),
            "time_label":       o.time_label,
            "confidence":       o.confidence,
        }


# ── Main detection engine ─────────────────────────────────────────────────────

class DetectionEngine:
    """
    Runs in a background thread.
    Reads video frames → detects objects → tracks them → triggers Raman scans
    on suspicious objects → pushes results to EngineState.
    """

    def __init__(
        self,
        video_source,           # path or camera index
        first_frame_path: str,
        station:   str = "New Delhi Railway Station",
        camera_id: str = "CAM-01",
        platform:  str = "Platform 4",
        coach:     str = "Coach B3",
    ):
        self.video_source      = video_source
        self.first_frame_path  = first_frame_path
        self.station           = station
        self.camera_id         = camera_id
        self.location          = f"{platform} – {coach}"

        self.tracker   = ObjectTracker()
        self.spectrometer = RamanSpectrometer(station=station, camera_id=camera_id)
        self.state     = EngineState()

        self._running  = False
        self._thread: Optional[threading.Thread] = None

        # Track which object IDs have already triggered a Raman scan
        # to avoid repeated scans for the same abandonment event
        self._scanned_ids: set = set()
        self._alerted_ids: set = set()

    # ── lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        log.info("Detection engine started  source=%s", self.video_source)

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)
        log.info("Detection engine stopped.")

    # ── main loop ─────────────────────────────────────────────────────────────

    def _run(self):
        # Load reference frame
        first_frame = cv2.imread(self.first_frame_path)
        if first_frame is None:
            log.warning("Reference frame not found – using live first frame.")
            first_frame_gray = None
        else:
            first_frame_gray = self._preprocess(first_frame)

        cap = cv2.VideoCapture(self.video_source)
        if not cap.isOpened():
            log.error("Cannot open video source: %s", self.video_source)
            self._running = False
            return

        fps_counter = 0
        fps_timer   = time.time()
        fps         = 0.0

        while self._running:
            ret, frame = cap.read()
            if not ret:
                # Loop video
                cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                self.tracker.reset()
                self._scanned_ids.clear()
                self._alerted_ids.clear()
                continue

            # Use first real frame as reference if file not found
            if first_frame_gray is None:
                first_frame_gray = self._preprocess(frame.copy())

            detections = self._detect(frame, first_frame_gray)
            tracked, abandoned = self.tracker.update(detections)

            # ── Raman scans for newly suspicious objects ──────────────────
            raman_results: List[RamanScanResult] = []
            new_alerts:    List[ThreatAlert]     = []

            for obj in abandoned:
                if obj.obj_id not in self._scanned_ids:
                    result = self.spectrometer.scan(object_id=obj.obj_id)
                    raman_results.append(result)
                    self._scanned_ids.add(obj.obj_id)
                    log.info(
                        "Raman scan obj=%d  substance=%s  risk=%d  confidence=%.2f",
                        obj.obj_id, result.substance, result.risk_level, result.confidence,
                    )

                # Generate alert when object hits WARNING threshold (first time only)
                if obj.obj_id not in self._alerted_ids:
                    raman_data = next(
                        (r.to_dict() for r in raman_results if True), None
                    )
                    alert = ThreatAlert(
                        alert_id   = str(uuid.uuid4())[:8].upper(),
                        object_id  = obj.obj_id,
                        status     = obj.status,
                        location   = self.location,
                        camera_id  = self.camera_id,
                        station    = self.station,
                        bbox       = [obj.x, obj.y, obj.w, obj.h],
                        confidence = obj.confidence,
                        raman      = raman_data,
                    )
                    new_alerts.append(alert)
                    self._alerted_ids.add(obj.obj_id)
                    log.warning("ALERT raised  id=%s  obj=%d  status=%s", alert.alert_id, obj.obj_id, obj.status)

            # ── Draw overlays ─────────────────────────────────────────────
            annotated = self._draw(frame.copy(), tracked)

            # Encode frame as JPEG for streaming
            _, jpeg = cv2.imencode(
                ".jpg", annotated,
                [int(cv2.IMWRITE_JPEG_QUALITY), 75]
            )

            # ── FPS calculation ───────────────────────────────────────────
            fps_counter += 1
            if time.time() - fps_timer >= 1.0:
                fps = fps_counter / (time.time() - fps_timer)
                fps_counter = 0
                fps_timer   = time.time()

            self.state.update(
                frame_bytes  = jpeg.tobytes(),
                tracked      = tracked,
                abandoned    = abandoned,
                new_alerts   = new_alerts,
                fps          = fps,
                raman_results= raman_results,
            )

        cap.release()

    # ── frame processing ──────────────────────────────────────────────────────

    @staticmethod
    def _preprocess(frame: np.ndarray) -> np.ndarray:
        gray  = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (3, 3), 0)
        return blurred

    def _detect(self, frame: np.ndarray, ref_gray: np.ndarray) -> List[List[int]]:
        frame_gray = self._preprocess(frame)

        diff   = cv2.absdiff(ref_gray, frame_gray)
        edged  = cv2.Canny(diff, 5, 200)
        kernel = np.ones((10, 10), np.uint8)
        thresh = cv2.morphologyEx(edged, cv2.MORPH_CLOSE, kernel, iterations=2)

        cnts, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

        detections = []
        for c in cnts:
            area = cv2.contourArea(c)
            if 50 < area < 10000:
                x, y, w, h = cv2.boundingRect(c)
                detections.append([x, y, w, h])
        return detections

    @staticmethod
    def _draw(frame: np.ndarray, tracked: List[TrackedObject]) -> np.ndarray:
        """Draw bounding boxes + status overlays on frame."""
        COLOR_MAP = {
            "NORMAL":   (0, 200, 0),    # green
            "WARNING":  (0, 165, 255),  # orange
            "CRITICAL": (0, 0, 255),    # red
        }

        h, w = frame.shape[:2]

        # Timestamp watermark
        ts = time.strftime("%d-%m-%Y  %H:%M:%S")
        cv2.putText(frame, ts, (10, h - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)

        for obj in tracked:
            color = COLOR_MAP.get(obj.status, (0, 200, 0))

            # Draw bounding box
            cv2.rectangle(frame, (obj.x, obj.y), (obj.x + obj.w, obj.y + obj.h), color, 2)

            # Label
            label = f"ID:{obj.obj_id}  {obj.time_label}"
            if obj.status != "NORMAL":
                label = f"[{obj.status}] " + label

            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
            cv2.rectangle(frame,
                          (obj.x, obj.y - th - 8),
                          (obj.x + tw + 4, obj.y),
                          color, -1)
            cv2.putText(frame, label,
                        (obj.x + 2, obj.y - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

            # Confidence bar (only for suspicious objects)
            if obj.status != "NORMAL":
                bar_w = int(obj.w * obj.confidence)
                cv2.rectangle(frame,
                              (obj.x, obj.y + obj.h + 2),
                              (obj.x + obj.w, obj.y + obj.h + 8),
                              (50, 50, 50), -1)
                cv2.rectangle(frame,
                              (obj.x, obj.y + obj.h + 2),
                              (obj.x + bar_w, obj.y + obj.h + 8),
                              color, -1)

        return frame
