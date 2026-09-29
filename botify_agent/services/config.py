"""Installation settings (``ir.config_parameter``, written from Settings).

Reading them needs ``sudo()``: parameters are admin-only and the shared
secret must never be readable by employees. This is configuration access,
not the execution path: operations never run with elevated rights.
"""

from .classify import RISK_CLASSES

PREFIX = "botify_agent."


def _param(env, key, default=None):
    return env["ir.config_parameter"].sudo().get_param(PREFIX + key, default)


def get_settings(env):
    enabled_classes = ["read"]
    for risk_class in RISK_CLASSES[1:]:
        if _param(env, "allow_" + risk_class) == "True":
            enabled_classes.append(risk_class)
    return {
        "enabled": _param(env, "enabled") == "True",
        "api_url": (_param(env, "api_url") or "").rstrip("/"),
        "installation_key": _param(env, "installation_key") or "",
        "enabled_classes": enabled_classes,
        "retention_days": int(_param(env, "retention_days") or 90),
    }


def get_secret(env):
    return _param(env, "secret") or ""


def configured(env):
    """Enabled and fully configured (Settings -> Botify Agent)."""
    settings = get_settings(env)
    return bool(settings["enabled"] and get_secret(env) and settings["installation_key"] and settings["api_url"])
