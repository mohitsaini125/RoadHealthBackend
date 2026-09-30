"""
Integration boundary for the road-damage AI model.

Report controllers/services call only `assess_image()` — they never import
httpx or touch the Roboflow API directly.

Roboflow's hosted inference API is used for rdd-india/9. The API key and
model configuration are read only from environment-backed settings.
"""
import base64
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

_CLASS_LABEL_MAP: dict[str, str] = {
    "D00": "Longitudinal Crack",
    "D20": "Transverse Crack",
    "D40": "Alligator Crack",
    "D44": "Pothole",
}

_CONFIDENCE_SEVERITY: list[tuple[float, str]] = [
    (0.80, "critical"),
    (0.60, "high"),
    (0.40, "medium"),
    (0.00, "low"),
]

_ROBOFLOW_TIMEOUT_S = 30


@dataclass
class AIResult:
    damage_type: str | None
    confidence: float | None
    bounding_boxes: dict | None
    estimated_severity: str | None
    model_version: str
    processed_at: datetime


class AIServiceUnavailableError(Exception):
    """Raised when Roboflow is unreachable or returns an unusable response."""


class _RoboflowBackend:
    def __init__(self) -> None:
        self._api_key = settings.ROBOFLOW_API_KEY.strip()
        self._model_id = settings.ROBOFLOW_MODEL_ID.strip().strip("/")
        self._api_url = settings.ROBOFLOW_API_URL.rstrip("/")

        if not self._api_key:
            raise AIServiceUnavailableError(
                "ROBOFLOW_API_KEY is not configured. Add it to backend/.env and restart FastAPI."
            )
        if not self._model_id:
            raise AIServiceUnavailableError("ROBOFLOW_MODEL_ID is not configured.")

    def _read_image_b64(self, image_path: str) -> str:
        abs_path = Path(image_path)
        if not abs_path.exists():
            raise AIServiceUnavailableError(
                f"Image file not found for AI assessment: {abs_path}"
            )
        try:
            with abs_path.open("rb") as fh:
                image_bytes = fh.read()
        except OSError as exc:
            raise AIServiceUnavailableError(
                f"Could not read image for AI assessment: {exc}"
            ) from exc
        if not image_bytes:
            raise AIServiceUnavailableError("The uploaded image is empty.")
        return base64.b64encode(image_bytes).decode("ascii")

    def _call_roboflow(self, image_b64: str) -> dict[str, Any]:
        # Roboflow's hosted detection API accepts a base64 image in the raw
        # POST body with application/x-www-form-urlencoded content type.
        url = f"{self._api_url}/{self._model_id}"
        params = {"api_key": self._api_key, "format": "json"}
        headers = {"Content-Type": "application/x-www-form-urlencoded"}

        try:
            response = httpx.post(
                url,
                params=params,
                content=image_b64,
                headers=headers,
                timeout=_ROBOFLOW_TIMEOUT_S,
            )
        except httpx.TimeoutException as exc:
            raise AIServiceUnavailableError(
                f"Roboflow request timed out after {_ROBOFLOW_TIMEOUT_S}s."
            ) from exc
        except httpx.RequestError as exc:
            raise AIServiceUnavailableError(
                f"Roboflow request failed: {type(exc).__name__}."
            ) from exc

        if response.status_code >= 400:
            # Never include the API key in the error. The response body is
            # useful for diagnosing invalid keys/model IDs without exposing secrets.
            detail = response.text.strip().replace("\n", " ")[:500]
            raise AIServiceUnavailableError(
                f"Roboflow returned HTTP {response.status_code}: {detail or 'no response body'}"
            )

        try:
            payload = response.json()
        except ValueError as exc:
            raise AIServiceUnavailableError(
                "Roboflow returned a non-JSON response."
            ) from exc

        if not isinstance(payload, dict):
            raise AIServiceUnavailableError("Roboflow returned an invalid response shape.")
        return payload

    @staticmethod
    def _severity_from_confidence(confidence: float) -> str:
        for threshold, severity in _CONFIDENCE_SEVERITY:
            if confidence >= threshold:
                return severity
        return "low"

    def predict(self, image_path: str) -> AIResult:
        image_b64 = self._read_image_b64(image_path)
        raw = self._call_roboflow(image_b64)

        predictions = raw.get("predictions", [])
        if not isinstance(predictions, list):
            raise AIServiceUnavailableError(
                "Roboflow response has an invalid predictions field."
            )

        if not predictions:
            # A valid inference with no detected damage is different from an
            # inference failure. Keep the assessment successful but empty.
            return AIResult(
                damage_type=None,
                confidence=None,
                bounding_boxes={"predictions": []},
                estimated_severity=None,
                model_version=self._model_id,
                processed_at=datetime.now(timezone.utc),
            )

        known = [
            p for p in predictions
            if isinstance(p, dict) and p.get("class") in _CLASS_LABEL_MAP
        ]
        working = known if known else [p for p in predictions if isinstance(p, dict)]
        if not working:
            raise AIServiceUnavailableError("Roboflow returned no usable predictions.")

        def confidence_of(prediction: dict[str, Any]) -> float:
            try:
                value = float(prediction.get("confidence", 0.0))
            except (TypeError, ValueError):
                value = 0.0
            return max(0.0, min(1.0, value))

        primary = max(working, key=confidence_of)
        primary_class = str(primary.get("class") or "")
        primary_confidence = confidence_of(primary)
        damage_type = _CLASS_LABEL_MAP.get(primary_class, primary_class) or None
        severity = self._severity_from_confidence(primary_confidence)

        bounding_boxes = {
            "predictions": [
                {
                    "class": p.get("class"),
                    "confidence": round(confidence_of(p), 4),
                    "x": p.get("x"),
                    "y": p.get("y"),
                    "width": p.get("width"),
                    "height": p.get("height"),
                }
                for p in predictions
                if isinstance(p, dict)
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


def assess_image(image_path: str) -> AIResult:
    """Run a real Roboflow assessment. AI failures are never silently stubbed."""
    return _RoboflowBackend().predict(image_path)
