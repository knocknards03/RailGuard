"""
RailGuard - Raman Spectrometer Simulator
Simulates trace chemical analysis results from a miniaturised Raman spectrometer.
In production, replace simulate_scan() with actual serial/USB driver calls
to your hardware (e.g. Wasatch Photonics, Ocean Insight, etc.)

Threat library based on characteristic Raman shift peaks (cm⁻¹).
"""

import random
import time
from dataclasses import dataclass, field
from typing import List, Optional


# ── Known chemical signatures ────────────────────────────────────────────────
# Each entry: (name, category, peak_shifts, description, risk_level 1-5)
CHEMICAL_LIBRARY = [
    # ── Explosives ────────────────────────────────────────────────────────────
    {
        "name": "RDX",
        "category": "EXPLOSIVE",
        "peaks": [885, 1268, 1315, 1556],
        "description": "Cyclotrimethylenetrinitramine – military-grade explosive",
        "risk": 5,
        "color": "#ff2020",
    },
    {
        "name": "TNT",
        "category": "EXPLOSIVE",
        "peaks": [826, 1080, 1360, 1558],
        "description": "Trinitrotoluene – common IED component",
        "risk": 5,
        "color": "#ff2020",
    },
    {
        "name": "PETN",
        "category": "EXPLOSIVE",
        "peaks": [870, 1278, 1380, 1657],
        "description": "Pentaerythritol tetranitrate – detonator explosive",
        "risk": 5,
        "color": "#ff2020",
    },
    {
        "name": "TATP",
        "category": "EXPLOSIVE",
        "peaks": [575, 800, 883, 1200],
        "description": "Triacetone triperoxide – improvised peroxide explosive",
        "risk": 5,
        "color": "#ff2020",
    },
    {
        "name": "Ammonium Nitrate",
        "category": "EXPLOSIVE_PRECURSOR",
        "peaks": [1040, 1322, 1680],
        "description": "Fertiliser-grade AN – explosive precursor",
        "risk": 3,
        "color": "#ff8800",
    },
    # ── Narcotics ─────────────────────────────────────────────────────────────
    {
        "name": "Heroin",
        "category": "NARCOTIC",
        "peaks": [785, 1004, 1248, 1601],
        "description": "Diacetylmorphine – Class-A opiate",
        "risk": 4,
        "color": "#ff4444",
    },
    {
        "name": "Cocaine",
        "category": "NARCOTIC",
        "peaks": [712, 1004, 1283, 1600],
        "description": "Cocaine hydrochloride – stimulant narcotic",
        "risk": 4,
        "color": "#ff4444",
    },
    {
        "name": "Methamphetamine",
        "category": "NARCOTIC",
        "peaks": [790, 1003, 1208, 1583],
        "description": "Crystal meth – Schedule-I stimulant",
        "risk": 4,
        "color": "#ff4444",
    },
    {
        "name": "Cannabis Resin",
        "category": "NARCOTIC",
        "peaks": [1004, 1157, 1520, 1630],
        "description": "Hashish / charas resin",
        "risk": 2,
        "color": "#ffcc00",
    },
    # ── Clean baseline ────────────────────────────────────────────────────────
    {
        "name": "Clean",
        "category": "CLEAR",
        "peaks": [],
        "description": "No threat substances detected",
        "risk": 0,
        "color": "#00e676",
    },
]


@dataclass
class RamanScanResult:
    substance:   str
    category:    str
    risk_level:  int            # 0 – 5
    confidence:  float          # 0.0 – 1.0
    description: str
    color:       str
    peaks_found: List[int]
    snr_db:      float          # signal-to-noise ratio in dB
    scan_time_ms: int
    timestamp:   float = field(default_factory=time.time)

    @property
    def is_threat(self) -> bool:
        return self.risk_level >= 2

    @property
    def threat_label(self) -> str:
        if self.risk_level == 0:
            return "CLEAR"
        if self.risk_level <= 2:
            return "LOW"
        if self.risk_level <= 3:
            return "MODERATE"
        if self.risk_level == 4:
            return "HIGH"
        return "CRITICAL"

    def to_dict(self) -> dict:
        return {
            "substance":    self.substance,
            "category":     self.category,
            "risk_level":   self.risk_level,
            "confidence":   self.confidence,
            "description":  self.description,
            "color":        self.color,
            "peaks_found":  self.peaks_found,
            "snr_db":       self.snr_db,
            "scan_time_ms": self.scan_time_ms,
            "timestamp":    self.timestamp,
            "is_threat":    self.is_threat,
            "threat_label": self.threat_label,
        }


class RamanSpectrometer:
    """
    Simulated Raman spectrometer interface.
    Call scan() to get a RamanScanResult.

    Simulation logic:
      - 85% of scans return CLEAR (normal background)
      - 15% inject a random threat from the library
      - SNR and confidence are randomised within realistic ranges
    """

    THREAT_PROBABILITY = 0.15   # change to 1.0 to always trigger threats (for demo)

    def __init__(self, station: str = "Platform-1", camera_id: str = "CAM-01"):
        self.station   = station
        self.camera_id = camera_id
        self._scan_count = 0

    # ── public ───────────────────────────────────────────────────────────────

    def scan(self, object_id: Optional[int] = None) -> RamanScanResult:
        """Perform a simulated Raman scan and return classified results."""
        start = time.time()
        time.sleep(random.uniform(0.05, 0.15))   # simulate hardware latency

        self._scan_count += 1

        if random.random() < self.THREAT_PROBABILITY:
            # Pick a random non-clear substance
            threats = [c for c in CHEMICAL_LIBRARY if c["category"] != "CLEAR"]
            chem = random.choice(threats)
        else:
            chem = next(c for c in CHEMICAL_LIBRARY if c["category"] == "CLEAR")

        # Simulate detected peaks with slight noise
        peaks = [p + random.randint(-5, 5) for p in chem["peaks"]]

        snr_db     = round(random.uniform(18.0, 42.0), 1)
        confidence = self._confidence(chem, snr_db)
        elapsed_ms = int((time.time() - start) * 1000)

        return RamanScanResult(
            substance    = chem["name"],
            category     = chem["category"],
            risk_level   = chem["risk"],
            confidence   = confidence,
            description  = chem["description"],
            color        = chem["color"],
            peaks_found  = peaks,
            snr_db       = snr_db,
            scan_time_ms = elapsed_ms,
        )

    def force_scan(self, substance_name: str) -> RamanScanResult:
        """Force a specific substance result – useful for demos."""
        chem = next(
            (c for c in CHEMICAL_LIBRARY if c["name"].lower() == substance_name.lower()),
            None,
        )
        if chem is None:
            raise ValueError(f"Unknown substance: {substance_name}")
        peaks      = [p + random.randint(-3, 3) for p in chem["peaks"]]
        snr_db     = round(random.uniform(22.0, 38.0), 1)
        confidence = self._confidence(chem, snr_db)
        return RamanScanResult(
            substance    = chem["name"],
            category     = chem["category"],
            risk_level   = chem["risk"],
            confidence   = confidence,
            description  = chem["description"],
            color        = chem["color"],
            peaks_found  = peaks,
            snr_db       = snr_db,
            scan_time_ms = random.randint(80, 200),
        )

    # ── private ──────────────────────────────────────────────────────────────

    @staticmethod
    def _confidence(chem: dict, snr_db: float) -> float:
        """Higher SNR → higher confidence. Clear scans always near 0.95+."""
        base = 0.55 + (snr_db - 18) / (42 - 18) * 0.35   # 0.55 – 0.90
        noise = random.uniform(-0.05, 0.05)
        if chem["category"] == "CLEAR":
            return round(min(0.99, 0.92 + random.uniform(0, 0.06)), 3)
        return round(min(0.98, max(0.50, base + noise)), 3)
