import json
import logging
from datetime import timedelta

from odoo import SUPERUSER_ID, api, fields, models

_logger = logging.getLogger(__name__)


class BotifyAgentOperation(models.Model):
    """One agent operation executed in this database: who, what, which
    records, the outcome. It is also the single-use claim of the grant's
    ``call_id``: a replayed grant returns the stored result.

    Rows are written by the module only (``sudo`` on this audit model, never
    on the operation itself); employees cannot read or write them.
    """

    _name = "botify.agent.operation"
    _description = "Botify agent operation"
    _order = "id desc"
    _rec_name = "call_id"

    call_id = fields.Char(required=True, readonly=True, index=True)
    run_id = fields.Char(readonly=True)
    botify_session_id = fields.Char(readonly=True)
    approval_id = fields.Char(readonly=True)
    user_id = fields.Many2one("res.users", required=True, readonly=True, ondelete="restrict")
    company_id = fields.Many2one("res.company", readonly=True)
    operation = fields.Char(readonly=True)
    model = fields.Char(readonly=True)
    method = fields.Char(readonly=True)
    record_ids = fields.Char(readonly=True)
    risk_class = fields.Char(readonly=True)
    status = fields.Selection(
        [("running", "Running"), ("done", "Done"), ("failed", "Failed"), ("aborted", "Rolled back")],
        required=True,
        readonly=True,
        default="running",
        help="Rolled back: the request's transaction did not commit, so nothing it did was kept; "
        "recorded in a separate transaction.",
    )
    error_code = fields.Char(readonly=True)
    error_message = fields.Char(readonly=True)
    latency_ms = fields.Integer(readonly=True)
    result_json = fields.Text(readonly=True, help="Kept briefly so a replayed grant gets the same answer.")

    _unique_call = models.Constraint("unique(call_id)", "An operation grant is used once.")

    @api.model
    def claimed(self, call_id):
        return self.sudo().search([("call_id", "=", call_id)], limit=1)

    @api.model
    def _claim_values(self, grant, env):
        operation = grant["op"]
        ids = operation.get("ids") or []
        return {
            "call_id": grant["callId"],
            "run_id": grant["runId"],
            "botify_session_id": grant["sessionId"],
            "approval_id": grant.get("approvalId"),
            "user_id": env.uid,
            "company_id": env.company.id,
            "operation": operation.get("op"),
            "model": operation.get("model"),
            "method": operation.get("method"),
            "record_ids": ",".join(str(i) for i in ids[:50]),
            "risk_class": grant["riskClass"],
        }

    @api.model
    def claim(self, grant, env, aborted=None):
        """Takes the grant's single use in the request transaction, so the
        outcome commits atomically with the operation. An ``aborted`` row
        (a transaction that never committed) is taken again: nothing of it
        was kept, so running it once more is still running it once.

        If this transaction then does not commit, for any reason (a failure
        after the operation's savepoint, at commit time, a serialization
        retry), ``_abort_evidence`` records it in a transaction of its own.
        """
        values = self._claim_values(grant, env)
        if aborted:
            aborted.sudo().write(dict(values, status="running", error_code=False, error_message=False, result_json=False))
            row = aborted
        else:
            row = self.sudo().create(values)
        env.cr.postrollback.add(self._abort_evidence(env.registry, values))
        return row

    @api.model
    def _abort_evidence(self, registry, values):
        def record():
            try:
                with registry.cursor() as cr:
                    operations = api.Environment(cr, SUPERUSER_ID, {})[self._name]
                    if not operations.search_count([("call_id", "=", values["call_id"])]):
                        operations.create(
                            dict(
                                values,
                                status="aborted",
                                error_code="TRANSACTION_ABORTED",
                                error_message="The Odoo transaction was rolled back: nothing was changed.",
                            )
                        )
            except Exception:  # noqa: BLE001 - evidence is best effort once the request is lost
                _logger.exception("botify_agent: could not record rolled-back operation %s", values["call_id"])

        return record

    def finish(self, answer, latency_ms):
        self.ensure_one()
        values = {"latency_ms": latency_ms, "result_json": json.dumps(answer, default=str)}
        if answer["ok"]:
            values["status"] = "done"
        else:
            values.update(status="failed", error_code=answer["error"]["code"], error_message=answer["error"]["message"])
        self.sudo().write(values)

    def answer(self):
        self.ensure_one()
        return json.loads(self.result_json) if self.result_json else None

    @api.model
    def _gc(self):
        """Stored answers are needed only while a grant can be replayed; rows
        are kept for the configured retention."""
        from ..services.config import get_settings

        now = fields.Datetime.now()
        self.sudo().search([("result_json", "!=", False), ("create_date", "<", now - timedelta(hours=1))]).write(
            {"result_json": False}
        )
        days = get_settings(self.env)["retention_days"]
        self.sudo().search([("create_date", "<", now - timedelta(days=days))]).unlink()
