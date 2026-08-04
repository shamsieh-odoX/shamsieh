# -*- coding: utf-8 -*-


class ZktecoError(Exception):
    """Base error for ZKTeco device communication."""


class ZktecoConnectionError(ZktecoError):
    """Raised when the device cannot be reached or authenticated."""


class ZktecoDependencyError(ZktecoError):
    """Raised when the optional pyzk package is missing."""
