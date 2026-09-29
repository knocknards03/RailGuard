"""
RailGuard - Flask Backend
Serves the dashboard UI and exposes REST + SSE endpoints consumed by the frontend.
"""

import os
import time
import json
import logging
import threading
from flask import (
    Flask, render_template, Response, jsonify,
    request, stream_with_context
)
from detection_engine import DetectionEngine

log = logging.getLogger("railguard.app")

# ── App setup ────────────────────────────────────────────────────────────────
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "railguard-dev-secret")

# ── Detection engine ─────────────────────────────────────────────────────────
BASE_DIR   = os.path.dirname(os.path.abspath(__file__))
VIDEO_SRC  = os.environ.get("VIDEO_SRC",  os.path.join(BASE_DIR, "cut.mp4"))
REF_FRAME  = os.environ.get("REF_FRAME",  os.path.join(BASE_DIR, "Frame.png"))

# Auto-generate demo assets if they are missing
def _ensure_demo_assets():
    if not os.path.exists(VIDEO_SRC) or not os.path.exists(REF_FRAME):
        log.info("Demo assets missing — generating cut.mp4 and Frame.png …")
        try:
            import generate_demo_video
            generate_demo_video.generate()
            log.info("Demo assets generated successfully.")
        except Exception as e:
            log.error("Failed to generate demo assets: %s", e)

_ensure_demo_assets()

engine = DetectionEngine(
    video_source      = VIDEO_SRC,
    first_frame_path  = REF_FRAME,
    station           = "New Delhi Railway Station",
    camera_id         = "CAM-04",
    platform          = "Platform 4",
    coach             = "Coach B3",
)

# Start engine in background when the module loads (works with Flask dev server)
_engine_started = False
_start_lock     = threading.Lock()

def ensure_engine():
    global _engine_started
    with _start_lock:
        if not _engine_started:
            engine.start()
            _engine_started = True


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    ensure_engine()
    return render_template("index.html")


# ── Video stream (MJPEG) ──────────────────────────────────────────────────────

def _generate_frames():
    """Yield MJPEG frames from the detection engine."""
    while True:
        frame = engine.state.get_frame()
        if frame:
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n" + frame + b"\r\n"
            )
        time.sleep(1 / 30)   # cap at ~30 fps


@app.route("/video_feed")
def video_feed():
    ensure_engine()
    return Response(
        _generate_frames(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


# ── SSE live dashboard updates ───────────────────────────────────────────────

@app.route("/stream")
def stream():
    """
    Server-Sent Events endpoint.
    Frontend subscribes once; receives JSON payload every second.
    """
    ensure_engine()

    def event_generator():
        last_alert_count = 0
        while True:
            payload = engine.state.get_dashboard_payload()

            # Flag new alerts so JS can trigger sound/notification
            current_count = payload["stats"]["total_alerts"]
            payload["new_alert"] = current_count > last_alert_count
            last_alert_count = current_count

            data = json.dumps(payload)
            yield f"data: {data}\n\n"
            time.sleep(1)

    return Response(
        stream_with_context(event_generator()),
        mimetype="text/event-stream",
        headers={
            "Cache-Control":   "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── REST API ──────────────────────────────────────────────────────────────────

@app.route("/api/stats")
def api_stats():
    ensure_engine()
    payload = engine.state.get_dashboard_payload()
    return jsonify(payload["stats"])


@app.route("/api/alerts")
def api_alerts():
    ensure_engine()
    alerts = engine.state.get_alerts()
    # Optional filter: ?status=CRITICAL or ?unacknowledged=1
    status_filter = request.args.get("status", "").upper()
    unack_only    = request.args.get("unacknowledged", "0") == "1"
    if status_filter:
        alerts = [a for a in alerts if a["status"] == status_filter]
    if unack_only:
        alerts = [a for a in alerts if not a["acknowledged"]]
    return jsonify({"alerts": alerts, "count": len(alerts)})


@app.route("/api/alerts/<alert_id>/acknowledge", methods=["POST"])
def acknowledge_alert(alert_id: str):
    ensure_engine()
    success = engine.state.acknowledge_alert(alert_id)
    if success:
        log.info("Alert %s acknowledged by operator.", alert_id)
        return jsonify({"ok": True, "message": f"Alert {alert_id} acknowledged. RPF notified."})
    return jsonify({"ok": False, "message": "Alert not found."}), 404


@app.route("/api/raman/history")
def raman_history():
    ensure_engine()
    payload = engine.state.get_dashboard_payload()
    return jsonify({"history": payload["raman_history"]})


@app.route("/api/raman/force_scan", methods=["POST"])
def force_raman_scan():
    """Demo endpoint: trigger a named-substance scan immediately."""
    ensure_engine()
    body = request.get_json(silent=True) or {}
    substance = body.get("substance", "RDX")
    try:
        result = engine.spectrometer.force_scan(substance)
        with engine.state._lock:
            engine.state.raman_history.append(result.to_dict())
            engine.state.stats["raman_scans"] += 1
            if result.is_threat:
                engine.state.stats["threats_detected"] += 1
        return jsonify({"ok": True, "result": result.to_dict()})
    except ValueError as e:
        return jsonify({"ok": False, "message": str(e)}), 400


@app.route("/api/system/status")
def system_status():
    ensure_engine()
    s = engine.state.stats
    return jsonify({
        "engine_running": engine._running,
        "uptime_seconds": s.get("uptime_seconds", 0),
        "fps":            s.get("fps", 0),
        "video_source":   os.path.basename(str(VIDEO_SRC)),
        "station":        engine.station,
        "camera_id":      engine.camera_id,
    })


# ── Error handlers ────────────────────────────────────────────────────────────

@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404


@app.errorhandler(500)
def server_error(e):
    return jsonify({"error": "Internal server error"}), 500


# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    ensure_engine()
    app.run(
        host  = "0.0.0.0",
        port  = int(os.environ.get("PORT", 5001)),
        debug = False,          # keep False – debug mode restarts the process
        threaded = True,
    )
