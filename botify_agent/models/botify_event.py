import json
import logging
import re
import uuid
from datetime import timedelta

from odoo import api, fields, models

from ..services import config

_logger = logging.getLogger(__name__)

KIND = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")
ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
FACTS_MAX_BYTES = 2048
LABEL_MAX = 200
LEASE = timedelta(seconds=60)
MAX_LEASE = timedelta(hours=1)
PENDING_DAYS = 7
BATCH = 10


def _fact(kind, value):
    if kind == "int":
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == "float":
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if kind == "str":
        # Counted as Botify counts (UTF-16 units), so Botify never rejects what Odoo accepted.
        return isinstance(value, str) and len(value.encode("utf-16-le")) // 2 <= LABEL_MAX
    if kind == "date":
        return isinstance(value, str) and bool(ISO_DATE.match(value))
    return False


class BotifyAgentEvent(models.Model):
    """Something in Odoo that the employee's Botify agent tells them about
    (a leave approved...). The row is the truth; the bus only wakes the
    employee's browser, which relays the signed event to Botify and brings
    back Botify's signed acknowledgement.

    Rows are created by producer modules through ``_notify`` (server code
    only) and written by this module with ``sudo``; employees have no access.
    """

    _name = "botify.agent.event"
    _description = "Botify agent notification event"
    _order = "id desc"
    _rec_name = "kind"

    event_id = fields.Char(required=True, readonly=True, index=True, default=lambda self: uuid.uuid4().hex)
    user_id = fields.Many2one("res.users", required=True, readonly=True, index=True, ondelete="cascade")
    company_id = fields.Many2one("res.company", readonly=True, ondelete="set null")
    kind = fields.Char(required=True, readonly=True)
    facts_json = fields.Text(required=True, readonly=True)
    state = fields.Selection(
        [
            ("pending", "Pending"),
            ("delivering", "Delivering"),
            ("delivered", "Delivered"),
            ("failed", "Failed"),
            ("expired", "Expired"),
        ],
        required=True,
        readonly=True,
        default="pending",
        index=True,
    )
    attempts = fields.Integer(readonly=True)
    lease_until = fields.Datetime(readonly=True)
    last_error = fields.Char(readonly=True)
    delivered_at = fields.Datetime(readonly=True)

    _unique_event = models.Constraint("unique(event_id)", "An event is delivered once.")

    @api.model
    def _botify_event_kinds(self):
        """``{kind: {fact: (type, required)}}``; producer modules extend it.
        Types: ``int``, ``float``, ``str`` (≤ 200 chars), ``date`` (ISO)."""
        return {}

    @api.model
    def _notify(self, user, kind, facts, company=None):
        """Records an event for ``user``, returns it, or ``False`` when it is
        not for Botify (integration off, user not a Botify user, bad kind or
        facts). Never raises: a notification must not block the business
        action that produced it."""
        try:
            with self.env.cr.savepoint():
                values = self._event_values(user, kind, facts, company)
                if not values:
                    return False
                event = self.sudo().create(values)
            user._bus_send("botify_agent/event", {})
            return event
        except Exception:  # noqa: BLE001 - the producer's transaction must go on
            _logger.exception("botify_agent: could not record %s event for user %s", kind, user.id)
            return False

    @api.model
    def _event_values(self, user, kind, facts, company):
        user = user.sudo()
        if len(user) != 1 or not user.active or user.share:
            _logger.info("botify_agent: %s event dropped, not an internal user", kind)
            return None
        if not config.configured(self.env):
            return None
        if not user.has_group("botify_agent.group_botify_user"):
            return None
        spec = self._botify_event_kinds().get(kind) if isinstance(kind, str) and KIND.match(kind) else None
        if spec is None:
            _logger.warning("botify_agent: unknown event kind %r", kind)
            return None
        clean = {key: value for key, value in (facts or {}).items() if value is not None}
        unknown = set(clean) - set(spec)
        missing = {key for key, (_type, required) in spec.items() if required and key not in clean}
        invalid = {key for key, value in clean.items() if key in spec and not _fact(spec[key][0], value)}
        if unknown or missing or invalid:
            _logger.warning(
                "botify_agent: %s event dropped, facts unknown=%s missing=%s invalid=%s",
                kind, sorted(unknown), sorted(missing), sorted(invalid),
            )
            return None
        facts_json = json.dumps(clean, separators=(",", ":"), sort_keys=True)
        if len(facts_json.encode()) > FACTS_MAX_BYTES:
            _logger.warning("botify_agent: %s event dropped, facts too large", kind)
            return None
        return {
            "user_id": user.id,
            "company_id": company.id if company and company in user.company_ids else False,
            "kind": kind,
            "facts_json": facts_json,
        }

    @api.model
    def _lease(self, user):
        """The user's events due for delivery, leased so another tab waits.
        Only an acknowledgement moves an event out of ``delivering``; without
        one the lease doubles (1 min … 1 h), so an outage or a tab that cannot
        deliver never wears an event out before it expires."""
        now = fields.Datetime.now()
        self.env.cr.execute(
            """SELECT id FROM botify_agent_event
                WHERE user_id = %s AND state IN ('pending', 'delivering')
                  AND (lease_until IS NULL OR lease_until < %s)
                ORDER BY id LIMIT %s FOR UPDATE SKIP LOCKED""",
            (user.id, now, BATCH),
        )
        rows = self.sudo().browse([row[0] for row in self.env.cr.fetchall()])
        for row in rows:
            lease = min(LEASE * 2 ** min(row.attempts, 6), MAX_LEASE)
            row.write({"state": "delivering", "attempts": row.attempts + 1, "lease_until": now + lease})
        return rows

    def _token_payload(self, settings, db):
        self.ensure_one()
        return {
            "iss": settings["installation_key"],
            "db": db,
            "uid": self.user_id.id,
            "eventId": self.event_id,
            "kind": self.kind,
            "facts": json.loads(self.facts_json),
            "company": {"id": self.company_id.id, "name": (self.company_id.name or "")[:120]}
            if self.company_id
            else None,
            "createdAt": self.create_date.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }

    @api.model
    def _acknowledge(self, user, ack):
        """Botify's verified receipt for one of ``user``'s own events;
        repeated receipts change nothing."""
        event = self.sudo().search([("event_id", "=", ack["eventId"]), ("user_id", "=", user.id)], limit=1)
        if not event:
            return False
        pending = event.filtered(lambda row: row.state in ("pending", "delivering"))
        outcome, reason = ack["outcome"], ack.get("reason")
        if outcome == "delivered":
            pending.write({"state": "delivered", "delivered_at": fields.Datetime.now(), "lease_until": False})
        else:
            pending.write({"state": "failed", "last_error": (reason or "rejected by Botify")[:200], "lease_until": False})
        return bool(pending)

    @api.model
    def _gc(self):
        """Undelivered events expire after a week; finished ones are kept for
        the configured retention."""
        now = fields.Datetime.now()
        events = self.sudo()
        events.search(
            [("state", "in", ("pending", "delivering")), ("create_date", "<", now - timedelta(days=PENDING_DAYS))]
        ).write({"state": "expired", "lease_until": False})
        days = config.get_settings(self.env)["retention_days"]
        events.search(
            [("state", "in", ("delivered", "failed", "expired")), ("create_date", "<", now - timedelta(days=days))]
        ).unlink()
