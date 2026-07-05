# -*- coding: utf-8 -*-


class HikvisionError(Exception):
    """Base exception for Hikvision ISAPI client errors."""


class HikvisionConnectionError(HikvisionError):
    """Network failure, timeout, or unreachable device."""


class HikvisionAuthenticationError(HikvisionError):
    """HTTP 401/403 or invalid credentials."""


class HikvisionEndpointNotFound(HikvisionError):
    """Required ISAPI endpoint returned HTTP 404."""


class HikvisionParseError(HikvisionError):
    """Malformed XML or JSON response from the device."""
