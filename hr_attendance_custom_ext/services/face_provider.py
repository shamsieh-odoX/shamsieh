# -*- coding: utf-8 -*-

from .face_provider_insightface import InsightFaceProvider, PROVIDER_NAME


def get_face_provider(company):
    """Return the configured face provider for a company."""
    provider_name = company.face_provider or PROVIDER_NAME
    quality_check_enabled = bool(company.face_quality_check_enabled)
    if provider_name == PROVIDER_NAME:
        return InsightFaceProvider(quality_check_enabled=quality_check_enabled)
    raise ValueError(f'Unsupported face provider: {provider_name}')
