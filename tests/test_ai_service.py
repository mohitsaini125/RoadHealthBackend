"""
Tests for app/services/ai_service.py

All tests use monkeypatching / mocking — NO real Roboflow API key is needed.
Run with:
    pytest tests/test_ai_service.py -v
"""
import base64
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import httpx
import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fake_image(tmp_path: Path) -> Path:
    """Write a minimal valid JPEG stub (just the SOI marker) for path-reading tests."""
    img = tmp_path / "test_road.jpg"
    img.write_bytes(b"\xff\xd8\xff" + b"\x00" * 16)  # JPEG SOI + padding
    return img


def _b64_encode(p: Path) -> str:
    return base64.b64encode(p.read_bytes()).decode("ascii")


# ---------------------------------------------------------------------------
# 1. Roboflow backend — successful detection
# ---------------------------------------------------------------------------

class TestRoboflowBackendSuccess:

    def test_single_prediction_mapped_correctly(self, tmp_path, monkeypatch):
        img = _make_fake_image(tmp_path)

        fake_response = {
            "predictions": [
                {
                    "class": "D40",
                    "confidence": 0.87,
                    "x": 320,
                    "y": 240,
                    "width": 64,
                    "height": 48,
                }
            ]
        }

        monkeypatch.setattr("app.config.settings.ROBOFLOW_API_KEY", "test-key")
        monkeypatch.setattr("app.config.settings.ROBOFLOW_MODEL_ID", "rdd-india/9")
        monkeypatch.setattr("app.config.settings.ROBOFLOW_API_URL", "https://detect.roboflow.com")

        with patch("httpx.post") as mock_post:
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = fake_response
            mock_post.return_value = resp

            from app.services.ai_service import _RoboflowBackend
            backend = _RoboflowBackend()
            result = backend.predict(str(img))

        assert result.damage_type == "Alligator Crack"
        assert abs(result.confidence - 0.87) < 1e-6
        assert result.estimated_severity == "critical"  # 0.87 >= 0.80
        assert result.model_version == "rdd-india/9"
        assert result.bounding_boxes is not None
        assert len(result.bounding_boxes["predictions"]) == 1

    def test_multiple_predictions_highest_confidence_is_primary(self, tmp_path, monkeypatch):
        img = _make_fake_image(tmp_path)

        fake_response = {
            "predictions": [
                {"class": "D00", "confidence": 0.55, "x": 100, "y": 100, "width": 30, "height": 20},
                {"class": "D20", "confidence": 0.72, "x": 200, "y": 150, "width": 50, "height": 40},
                {"class": "D44", "confidence": 0.91, "x": 300, "y": 200, "width": 80, "height": 60},
            ]
        }

        monkeypatch.setattr("app.config.settings.ROBOFLOW_API_KEY", "test-key")
        monkeypatch.setattr("app.config.settings.ROBOFLOW_MODEL_ID", "rdd-india/9")
        monkeypatch.setattr("app.config.settings.ROBOFLOW_API_URL", "https://detect.roboflow.com")

        with patch("httpx.post") as mock_post:
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = fake_response
            mock_post.return_value = resp

            from app.services.ai_service import _RoboflowBackend
            backend = _RoboflowBackend()
            result = backend.predict(str(img))

        # Highest confidence is D44 (0.91) → Pothole
        assert result.damage_type == "Pothole"
        assert abs(result.confidence - 0.91) < 1e-6
        assert result.estimated_severity == "critical"
        # All 3 boxes preserved
        assert len(result.bounding_boxes["predictions"]) == 3

    def test_no_predictions_returns_null_result(self, tmp_path, monkeypatch):
        img = _make_fake_image(tmp_path)

        monkeypatch.setattr("app.config.settings.ROBOFLOW_API_KEY", "test-key")
        monkeypatch.setattr("app.config.settings.ROBOFLOW_MODEL_ID", "rdd-india/9")
        monkeypatch.setattr("app.config.settings.ROBOFLOW_API_URL", "https://detect.roboflow.com")

        with patch("httpx.post") as mock_post:
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {"predictions": []}
            mock_post.return_value = resp

            from app.services.ai_service import _RoboflowBackend
            backend = _RoboflowBackend()
            result = backend.predict(str(img))

        assert result.damage_type is None
        assert result.confidence is None
        assert result.bounding_boxes == {"predictions": []}  # empty list, not None
        assert result.estimated_severity is None


# ---------------------------------------------------------------------------
# 2. Severity thresholds
# ---------------------------------------------------------------------------

class TestSeverityThresholds:

    @pytest.mark.parametrize("confidence,expected_severity", [
        (0.95, "critical"),
        (0.80, "critical"),
        (0.79, "high"),
        (0.60, "high"),
        (0.59, "medium"),
        (0.40, "medium"),
        (0.39, "low"),
        (0.00, "low"),
    ])
    def test_severity_from_confidence(self, confidence, expected_severity):
        from app.services.ai_service import _RoboflowBackend
        backend = _RoboflowBackend.__new__(_RoboflowBackend)
        assert backend._severity_from_confidence(confidence) == expected_severity


# ---------------------------------------------------------------------------
# 3. Error handling — Roboflow failures raise AIServiceUnavailableError
# ---------------------------------------------------------------------------

class TestRoboflowBackendErrors:

    def _make_backend(self, monkeypatch):
        monkeypatch.setattr("app.config.settings.ROBOFLOW_API_KEY", "test-key")
        monkeypatch.setattr("app.config.settings.ROBOFLOW_MODEL_ID", "rdd-india/9")
        monkeypatch.setattr("app.config.settings.ROBOFLOW_API_URL", "https://detect.roboflow.com")
        from app.services.ai_service import _RoboflowBackend
        return _RoboflowBackend()

    def test_timeout_raises_unavailable(self, tmp_path, monkeypatch):
        img = _make_fake_image(tmp_path)
        backend = self._make_backend(monkeypatch)

        with patch("httpx.post", side_effect=httpx.TimeoutException("timed out")):
            from app.services.ai_service import AIServiceUnavailableError
            with pytest.raises(AIServiceUnavailableError, match="timed out"):
                backend.predict(str(img))

    def test_http_error_raises_unavailable(self, tmp_path, monkeypatch):
        img = _make_fake_image(tmp_path)
        backend = self._make_backend(monkeypatch)

        with patch("httpx.post") as mock_post:
            resp = MagicMock()
            resp.raise_for_status.side_effect = httpx.HTTPStatusError(
                "403", request=MagicMock(), response=MagicMock(status_code=403)
            )
            mock_post.return_value = resp

            from app.services.ai_service import AIServiceUnavailableError
            with pytest.raises(AIServiceUnavailableError, match="HTTP 403"):
                backend.predict(str(img))

    def test_non_json_response_raises_unavailable(self, tmp_path, monkeypatch):
        img = _make_fake_image(tmp_path)
        backend = self._make_backend(monkeypatch)

        with patch("httpx.post") as mock_post:
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.side_effect = json.JSONDecodeError("not json", "", 0)
            mock_post.return_value = resp

            from app.services.ai_service import AIServiceUnavailableError
            with pytest.raises(AIServiceUnavailableError, match="non-JSON"):
                backend.predict(str(img))

    def test_missing_image_raises_unavailable(self, monkeypatch):
        monkeypatch.setattr("app.config.settings.ROBOFLOW_API_KEY", "test-key")
        monkeypatch.setattr("app.config.settings.ROBOFLOW_MODEL_ID", "rdd-india/9")
        monkeypatch.setattr("app.config.settings.ROBOFLOW_API_URL", "https://detect.roboflow.com")
        from app.services.ai_service import _RoboflowBackend, AIServiceUnavailableError
        backend = _RoboflowBackend()
        with pytest.raises(AIServiceUnavailableError, match="Image file not found"):
            backend.predict("/nonexistent/path/image.jpg")


# ---------------------------------------------------------------------------
# 4. Stub backend
# ---------------------------------------------------------------------------

class TestStubBackend:

    def test_stub_returns_null_with_stub_version(self, tmp_path):
        img = _make_fake_image(tmp_path)
        from app.services.ai_service import _StubBackend, MODEL_VERSION_STUB
        result = _StubBackend().predict(str(img))
        assert result.damage_type is None
        assert result.confidence is None
        assert result.bounding_boxes is None
        assert result.estimated_severity is None
        assert result.model_version == MODEL_VERSION_STUB


# ---------------------------------------------------------------------------
# 5. Factory — assess_image routes to stub when key is absent
# ---------------------------------------------------------------------------

class TestAssessImageFactory:

    def test_no_api_key_uses_stub(self, tmp_path, monkeypatch):
        img = _make_fake_image(tmp_path)
        monkeypatch.setattr("app.config.settings.ROBOFLOW_API_KEY", "")
        from app.services.ai_service import assess_image, MODEL_VERSION_STUB
        result = assess_image(str(img))
        assert result.model_version == MODEL_VERSION_STUB

    def test_api_key_set_uses_roboflow_backend(self, tmp_path, monkeypatch):
        img = _make_fake_image(tmp_path)
        monkeypatch.setattr("app.config.settings.ROBOFLOW_API_KEY", "test-key")
        monkeypatch.setattr("app.config.settings.ROBOFLOW_MODEL_ID", "rdd-india/9")
        monkeypatch.setattr("app.config.settings.ROBOFLOW_API_URL", "https://detect.roboflow.com")

        with patch("httpx.post") as mock_post:
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {
                "predictions": [
                    {"class": "D20", "confidence": 0.65, "x": 100, "y": 100, "width": 40, "height": 30}
                ]
            }
            mock_post.return_value = resp

            from app.services.ai_service import assess_image
            result = assess_image(str(img))

        assert result.damage_type == "Transverse Crack"
        assert result.model_version == "rdd-india/9"
        # API key must NOT appear in any logged/returned value
        assert "test-key" not in str(result)
