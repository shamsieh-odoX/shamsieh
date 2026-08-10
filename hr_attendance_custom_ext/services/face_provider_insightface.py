# -*- coding: utf-8 -*-
"""Self-hosted InsightFace provider (optional dependencies, lazy model load)."""

from __future__ import annotations

import base64
import logging
import math
from typing import Any

_logger = logging.getLogger(__name__)

PROVIDER_NAME = 'insightface'
UNAVAILABLE_MESSAGE = 'InsightFace provider is not installed or not configured.'

MIN_IMAGE_WIDTH = 320
MIN_IMAGE_HEIGHT = 320
MIN_BLUR_VARIANCE = 80.0
MIN_FACE_AREA_RATIO = 0.05

_MODEL_INSTANCE = None


class FaceProviderUnavailable(Exception):
    """Raised when InsightFace optional dependencies or model are unavailable."""


def haversine_distance_meters(lat1, lon1, lat2, lon2):
    """Return great-circle distance in meters between two WGS84 points."""
    radius = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(d_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    )
    return 2 * radius * math.asin(math.sqrt(a))


class InsightFaceProvider:
    """Lazy-loaded InsightFace wrapper for enrollment and verification."""

    def __init__(self, *, quality_check_enabled=True):
        self.quality_check_enabled = quality_check_enabled

    @staticmethod
    def is_available() -> bool:
        try:
            import cv2  # noqa: F401
            import insightface  # noqa: F401
            import numpy  # noqa: F401
            from PIL import Image  # noqa: F401
        except ImportError:
            return False
        return True

    def _require_available(self):
        if not self.is_available():
            raise FaceProviderUnavailable(UNAVAILABLE_MESSAGE)

    @classmethod
    def load_model(cls):
        global _MODEL_INSTANCE
        if _MODEL_INSTANCE is not None:
            return _MODEL_INSTANCE
        cls._require_available_static()
        from insightface.app import FaceAnalysis

        app = FaceAnalysis(name='buffalo_l', providers=['CPUExecutionProvider'])
        app.prepare(ctx_id=0, det_size=(640, 640))
        _MODEL_INSTANCE = app
        _logger.info('InsightFace model buffalo_l loaded')
        return _MODEL_INSTANCE

    @staticmethod
    def _require_available_static():
        if not InsightFaceProvider.is_available():
            raise FaceProviderUnavailable(UNAVAILABLE_MESSAGE)

    @staticmethod
    def _decode_image_bytes(image_bytes: bytes):
        import cv2
        import numpy as np

        if not image_bytes:
            raise ValueError('Empty image data')
        array = np.frombuffer(image_bytes, dtype=np.uint8)
        image = cv2.imdecode(array, cv2.IMREAD_COLOR)
        if image is None:
            raise ValueError('Could not decode image bytes')
        return image

    @classmethod
    def decode_base64_image(cls, image_base64: str) -> bytes:
        if not image_base64:
            raise ValueError('Missing image data')
        payload = image_base64
        if ',' in payload and payload.startswith('data:'):
            payload = payload.split(',', 1)[1]
        return base64.b64decode(payload)

    def image_quality_check(self, image_bytes: bytes) -> dict[str, Any]:
        import cv2

        image = self._decode_image_bytes(image_bytes)
        height, width = image.shape[:2]
        metrics = {
            'width': width,
            'height': height,
            'blur_variance': 0.0,
            'face_area_ratio': 0.0,
        }
        if width < MIN_IMAGE_WIDTH or height < MIN_IMAGE_HEIGHT:
            return {
                'passed': False,
                'reason': 'Image resolution too low',
                'metrics': metrics,
            }

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        blur_variance = float(cv2.Laplacian(gray, cv2.CV_64F).var())
        metrics['blur_variance'] = blur_variance
        if self.quality_check_enabled and blur_variance < MIN_BLUR_VARIANCE:
            return {
                'passed': False,
                'reason': 'Image is too blurry',
                'metrics': metrics,
            }

        faces = self.detect_faces(image_bytes)
        metrics['face_count'] = faces['face_count']
        if faces['face_count'] != 1:
            return {
                'passed': False,
                'reason': faces.get('failure_reason') or 'Face quality check failed',
                'metrics': metrics,
            }

        bbox = faces['faces'][0]['bbox']
        face_area = max(0.0, (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]))
        image_area = float(width * height)
        face_area_ratio = face_area / image_area if image_area else 0.0
        metrics['face_area_ratio'] = face_area_ratio
        if self.quality_check_enabled and face_area_ratio < MIN_FACE_AREA_RATIO:
            return {
                'passed': False,
                'reason': 'Face is too small in the image',
                'metrics': metrics,
            }

        return {'passed': True, 'reason': False, 'metrics': metrics}

    def detect_faces(self, image_bytes: bytes) -> dict[str, Any]:
        self._require_available()
        import numpy as np

        image = self._decode_image_bytes(image_bytes)
        model = self.load_model()
        faces = model.get(image)
        serialized = []
        for face in faces:
            bbox = face.bbox.tolist() if hasattr(face.bbox, 'tolist') else list(face.bbox)
            serialized.append({'bbox': bbox, 'det_score': float(getattr(face, 'det_score', 0.0))})

        result = {
            'face_count': len(serialized),
            'faces': serialized,
            'failure_reason': False,
        }
        if len(serialized) == 0:
            result['failure_reason'] = 'No face detected'
        elif len(serialized) > 1:
            result['failure_reason'] = 'Multiple faces detected'
        return result

    def extract_embedding(self, image_bytes: bytes) -> list[float]:
        self._require_available()
        if self.quality_check_enabled:
            quality = self.image_quality_check(image_bytes)
            if not quality['passed']:
                raise ValueError(quality['reason'])

        image = self._decode_image_bytes(image_bytes)
        model = self.load_model()
        faces = model.get(image)
        if len(faces) != 1:
            detection = self.detect_faces(image_bytes)
            raise ValueError(detection.get('failure_reason') or 'Face extraction failed')

        embedding = faces[0].normed_embedding
        if embedding is None:
            embedding = faces[0].embedding
        return embedding.tolist() if hasattr(embedding, 'tolist') else list(embedding)

    @staticmethod
    def compare_embeddings(embedding1, embedding2) -> dict[str, float]:
        import numpy as np

        vec1 = np.asarray(embedding1, dtype=np.float32)
        vec2 = np.asarray(embedding2, dtype=np.float32)
        if vec1.shape != vec2.shape:
            raise ValueError('Embedding dimensions do not match')

        norm1 = np.linalg.norm(vec1)
        norm2 = np.linalg.norm(vec2)
        if norm1 == 0 or norm2 == 0:
            return {'confidence_score': 0.0, 'distance': float(np.linalg.norm(vec1 - vec2))}

        cosine = float(np.dot(vec1, vec2) / (norm1 * norm2))
        cosine = max(-1.0, min(1.0, cosine))
        distance = float(np.linalg.norm(vec1 - vec2))
        return {
            'confidence_score': cosine,
            'distance': distance,
        }

    def verify_face(self, reference_embedding, selfie_image_bytes: bytes) -> dict[str, Any]:
        provider_response: dict[str, Any] = {}
        try:
            if self.quality_check_enabled:
                quality = self.image_quality_check(selfie_image_bytes)
                provider_response['quality'] = quality
                if not quality['passed']:
                    return {
                        'passed': False,
                        'confidence_score': 0.0,
                        'distance': 0.0,
                        'provider': PROVIDER_NAME,
                        'failure_reason': quality['reason'],
                        'provider_response': provider_response,
                    }

            live_embedding = self.extract_embedding(selfie_image_bytes)
            comparison = self.compare_embeddings(reference_embedding, live_embedding)
            provider_response['comparison'] = comparison
            return {
                'passed': True,
                'confidence_score': comparison['confidence_score'],
                'distance': comparison['distance'],
                'provider': PROVIDER_NAME,
                'failure_reason': False,
                'provider_response': provider_response,
            }
        except (FaceProviderUnavailable, ValueError) as exc:
            return {
                'passed': False,
                'confidence_score': 0.0,
                'distance': 0.0,
                'provider': PROVIDER_NAME,
                'failure_reason': str(exc),
                'provider_response': provider_response,
            }
