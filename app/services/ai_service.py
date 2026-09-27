"""
Integration boundary for the road-damage AI model. Report controllers/services
call only `assess_image()` — they never import YOLO/PyTorch directly.

If AI_MODEL_PATH is unset, falls back to a clearly-labeled development stub
so the rest of the backend stays testable end-to-end. The stub never claims
to be a real production result (model_version is tagged "stub").
"""
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from app.config import settings

MODEL_VERSION_STUB = "dev-stub-0.1"


@dataclass
class AIResult:
    damage_type: str | None
    confidence: float | None
    bounding_boxes: dict | None
    estimated_severity: str | None
    model_version: str
    processed_at: datetime


class AIServiceUnavailableError(Exception):
    pass


class _RealModelBackend:
    """Loads and runs the configured YOLOv8/PyTorch model. Implement when a
    trained model artifact is available at settings.AI_MODEL_PATH."""

    def __init__(self, model_path: str):
        self.model_path = model_path
        self._model = None  # lazy-loaded

    def _ensure_loaded(self):
        if self._model is not None:
            return
        try:
            from ultralytics import YOLO  # local import: optional heavy dependency
        except ImportError as exc:
            raise AIServiceUnavailableError(
                "AI_MODEL_PATH is set but the YOLO runtime is not installed."
            ) from exc
        self._model = YOLO(self.model_path)

    def predict(self, image_path: str) -> AIResult:
        self._ensure_loaded()
        results = self._model.predict(source=image_path, verbose=False)
        # NOTE: mapping from raw YOLO output to damage_type/severity is
        # project-specific and must be finalized once labels are defined.
        result = results[0] if results else None
        boxes = None
        confidence = None
        damage_type = None
        if result is not None and getattr(result, "boxes", None) is not None and len(result.boxes) > 0:
            top_box = result.boxes[0]
            confidence = float(top_box.conf[0]) if top_box.conf is not None else None
            cls_id = int(top_box.cls[0]) if top_box.cls is not None else None
            damage_type = result.names.get(cls_id) if cls_id is not None else None
            boxes = {"xyxy": [box.xyxy[0].tolist() for box in result.boxes]}

        return AIResult(
            damage_type=damage_type,
            confidence=confidence,
            bounding_boxes=boxes,
            estimated_severity=None,  # derived downstream from confidence/damage_type rules
            model_version=Path(self.model_path).stem,
            processed_at=datetime.now(timezone.utc),
        )


class _StubBackend:
    """Safe development stand-in — never presented to clients as a real AI result
    without the 'dev-stub' model_version tag being visible in the response."""

    def predict(self, image_path: str) -> AIResult:
        return AIResult(
            damage_type=None,
            confidence=None,
            bounding_boxes=None,
            estimated_severity=None,
            model_version=MODEL_VERSION_STUB,
            processed_at=datetime.now(timezone.utc),
        )


def _get_backend():
    if settings.AI_MODEL_PATH:
        return _RealModelBackend(settings.AI_MODEL_PATH)
    return _StubBackend()


def assess_image(image_path: str) -> AIResult:
    """Runs (or stubs) the AI assessment for a stored report image."""
    backend = _get_backend()
    return backend.predict(image_path)
