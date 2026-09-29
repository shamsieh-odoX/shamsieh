"""Odoo exceptions → the normalized errors Botify understands
(packages/connectors/odoo/src/client.ts ERROR_MAP)."""

import logging
import uuid

from psycopg2 import errors as pg_errors

from odoo.exceptions import AccessError, MissingError, UserError, ValidationError

_logger = logging.getLogger(__name__)
MAX_MESSAGE = 500


class OperationError(Exception):
    """A refusal decided by the module itself (never an Odoo traceback)."""

    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def error(code, message):
    return {"code": code, "message": str(message)[:MAX_MESSAGE]}


def normalize(exception):
    """``{code, message}``: Odoo's own user-facing message, never a traceback."""
    if isinstance(exception, OperationError):
        return error(exception.code, exception)
    if isinstance(exception, AccessError):
        return error("ACCESS_DENIED", exception.args[0] if exception.args else "access denied")
    if isinstance(exception, MissingError):
        return error("RECORD_NOT_FOUND", exception.args[0] if exception.args else "record not found")
    if isinstance(exception, (ValidationError, UserError)):
        return error("VALIDATION_FAILED", exception.args[0] if exception.args else "invalid")
    if isinstance(exception, (pg_errors.SerializationFailure, pg_errors.LockNotAvailable)):
        return error("CONFLICT", "the records are being changed by someone else; try again")
    reference = uuid.uuid4().hex[:12]
    _logger.exception("botify_agent: operation failed (ref %s)", reference)
    return error("INTERNAL", "Odoo could not complete the operation (ref %s)" % reference)
