"""
Integration boundary for the road-damage AI model.

Report controllers/services call only `assess_image()` — they never import
httpx or touch the Roboflow API directly.

Backend selection (resolved once at import time):
  • ROBOFLOW_API_KEY set  →  _RoboflowBackend  (live inference via HTTP)
  • ROBOFLOW_API_KEY unset →  _StubBackend     (clearly-labeled dev stub)

Error policy: Roboflow API errors are caught and re-raised as
AIServiceUnavailableError.  report_service treats that as a non-fatal event
and stores null AI fields rather than failing the entire report creation.
"""
import base64
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# ── Constants ──────────────────────────────────────────────────────────────

MODEL_VERSION_STUB = "dev-stub-0.1"

# RDD-India class names as returned by Roboflow (rdd-india/9).
# Map class label → human-readable damage type for storage.
_CLASS_LABEL_MAP: dict[str, str] = {
    "D00": "Longitudinal Crack",
    "D20": "Transverse Crack",
    "D40": "Alligator Crack",
    "D44": "Pothole",
}

# Severity thresholds derived from detection confidence.
# Adjust these once the project owner signs off on the mapping.
_CONFIDENCE_SEVERITY: list[tuple[float, str]] = [
    (0.80, "critical"),
    (0.60, "high"),
    (0.40, "medium"),
    (0.00, "low"),
]

_ROBOFLOW_TIMEOUT_S = 15  # seconds


# ── Data contract shared with the rest of the backend ─────────────────────

@dataclass
class AIResult:
    damage_type: str | None
    confidence: float | None
    bounding_boxes: dict | None
    estimated_severity: str | None
    model_version: str
    processed_at: datetime


class AIServiceUnavailableError(Exception):
    """Raised when Roboflow is unreachable or returns an unusable response.
    Callers should degrade gracefully (null AI fields) rather than 500-ing."""


# ── Roboflow backend ───────────────────────────────────────────────────────

class _RoboflowBackend:
    """Sends the stored image to the Roboflow Inference HTTP API and
    normalises the response into AIResult.  The API key is read from
    settings and is NEVER logged or included in any response."""

    def __init__(self) -> None:
        self._api_key = settings.ROBOFLOW_API_KEY
        self._model_id = settings.ROBOFLOW_MODEL_ID
        self._api_url = settings.ROBOFLOW_API_URL.rstrip("/")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _read_image_b64(self, image_path: str) -> str:
        """Read the image from disk and encode it as base64."""
        abs_path = Path(image_path)
        if not abs_path.is_absolute():
            # Relative paths are relative to the working directory (project root).
            abs_path = Path.cwd() / abs_path
        with abs_path.open("rb") as fh:
            return base64.b64encode(fh.read()).decode("ascii")

    def _call_roboflow(self, image_b64: str) -> dict[str, Any]:
        """POST the image to Roboflow and return the raw JSON dict.
        Auth is header-based (api_key_transport=header) — the key is never
        placed in the URL or logged."""
        url = f"{self._api_url}/{self._model_id}"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Bearer {self._api_key}",
        }
        data = f"image={image_b64}"

        try:
            response = httpx.post(
                url,
                content=data.encode(),
                headers=headers,
                timeout=_ROBOFLOW_TIMEOUT_S,
            )
            response.raise_for_status()
        except httpx.TimeoutException as exc:
            raise AIServiceUnavailableError(
                f"Roboflow request timed out after {_ROBOFLOW_TIMEOUT_S}s."
            ) from exc
        except httpx.HTTPStatusError as exc:
            # Avoid leaking the api_key that may appear in the request URL.
            raise AIServiceUnavailableError(
                f"Roboflow returned HTTP {exc.response.status_code}."
            ) from exc
        except httpx.RequestError as exc:
            raise AIServiceUnavailableError(
                f"Roboflow request failed: {type(exc).__name__}."
            ) from exc

        try:
            return response.json()
        except Exception as exc:
            raise AIServiceUnavailableError(
                "Roboflow returned a non-JSON body."
            ) from exc

    @staticmethod
    def _severity_from_confidence(confidence: float) -> str:
        for threshold, severity in _CONFIDENCE_SEVERITY:
            if confidence >= threshold:
                return severity
        return "low"

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def predict(self, image_path: str) -> AIResult:
        try:
            image_b64 = self._read_image_b64(image_path)
        except (OSError, FileNotFoundError) as exc:
            raise AIServiceUnavailableError(
                f"Could not read image for AI assessment: {exc}"
            ) from exc

        raw = self._call_roboflow(image_b64)

        predictions: list[dict] = raw.get("predictions", [])

        if not predictions:
            # No detections — return a valid result with null fields.
            logger.info("Roboflow returned 0 predictions for %s.", image_path)
            return AIResult(
                damage_type=None,
                confidence=None,
                bounding_boxes=None,
                estimated_severity=None,
                model_version=self._model_id,
                processed_at=datetime.now(timezone.utc),
            )

        # Filter to known RDD classes; keep all if none match (defensive).
        known = [p for p in predictions if p.get("class") in _CLASS_LABEL_MAP]
        working = known if known else predictions

        # Primary prediction = highest confidence.
        primary = max(working, key=lambda p: p.get("confidence", 0.0))
        primary_class = primary.get("class", "")
        primary_confidence = float(primary.get("confidence", 0.0))
        damage_type = _CLASS_LABEL_MAP.get(primary_class, primary_class) or None
        severity = self._severity_from_confidence(primary_confidence)

        # Preserve all bounding boxes in a structured dict.
        bounding_boxes = {
            "predictions": [
                {
                    "class": p.get("class"),
                    "confidence": round(float(p.get("confidence", 0.0)), 4),
                    "x": p.get("x"),
                    "y": p.get("y"),
                    "width": p.get("width"),
                    "height": p.get("height"),
                }
                for p in predictions
            ]
        }

        return AIResult(
            damage_type=damage_type,
            confidence=primary_confidence,
            bounding_boxes=bounding_boxes,
            estimated_severity=severity,
            model_version=self._model_id,
            processed_at=datetime.now(timezone.utc),
        )


# ── Stub backend ───────────────────────────────────────────────────────────

class _StubBackend:
    """Safe development stand-in.  model_version is tagged so no one mistakes
    this for a real prediction.  Used when ROBOFLOW_API_KEY is not set."""

    def predict(self, image_path: str) -> AIResult:
        logger.debug(
            "AI stub active (ROBOFLOW_API_KEY not set). "
            "Returning null assessment for %s.",
            image_path,
        )
        return AIResult(
            damage_type=None,
            confidence=None,
            bounding_boxes=None,
            estimated_severity=None,
            model_version=MODEL_VERSION_STUB,
            processed_at=datetime.now(timezone.utc),
        )


# ── Factory ────────────────────────────────────────────────────────────────

def _get_backend() -> _RoboflowBackend | _StubBackend:
    if settings.ROBOFLOW_API_KEY:
        return _RoboflowBackend()
    return _StubBackend()


# ── Public API ─────────────────────────────────────────────────────────────

def assess_image(image_path: str) -> AIResult:
    """Runs (or stubs) the AI assessment for a stored report image.

    On AIServiceUnavailableError the caller (report_service) should store
    null AI fields and continue — the report must not fail to save just
    because the AI backend is down.
    """
    backend = _get_backend()
    return backend.predict(image_path)
