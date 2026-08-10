/** @odoo-module **/

import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";

/**
 * Botify assistant client action.
 *
 * The flow, and why it is shaped this way:
 *
 *   1. Ask our own Odoo server for an identity assertion. It reads
 *      `request.env.user` server-side — this browser never states who it is.
 *   2. Hand the sealed assertion to Botify, which verifies the signature and
 *      returns an opaque session token.
 *   3. Chat using that token.
 *
 * The assertion passes through the browser but cannot be forged or edited: it
 * is HMAC-signed with a secret only the two servers hold. Tampering with it, or
 * with any field below, produces a token Botify rejects. Nothing in this file is
 * a security control — it is transport.
 */
class BotifyAssistant extends Component {
    static template = "botify_agent.Assistant";
    static props = {};

    setup() {
        this.rpc = useService("rpc");
        this.notification = useService("notification");
        this.state = useState({
            ready: false,
            error: null,
            messages: [],
            draft: "",
            sending: false,
            userName: "",
        });
        this.session = null;

        onWillStart(async () => {
            await this.connect();
        });
        onWillUnmount(() => {
            // Best-effort logout so the session dies with the tab rather than
            // waiting out its TTL.
            this.revoke();
        });
    }

    /** Steps 1 and 2: mint an assertion, exchange it for a Botify session. */
    async connect() {
        let identity;
        try {
            identity = await this.rpc("/botify_agent/identity", {});
        } catch {
            this.state.error = "Could not reach Odoo to establish your identity.";
            return;
        }
        if (!identity || identity.error) {
            this.state.error = identity?.error || "Botify is not configured.";
            return;
        }

        this.baseUrl = identity.base_url.replace(/\/+$/, "");
        this.agentId = identity.agent_id;
        this.state.userName = identity.user?.name || "";

        try {
            const response = await fetch(
                `${this.baseUrl}/api/chat/${this.agentId}/identity/exchange`,
                {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        platform: identity.platform,
                        assertion: identity.assertion,
                        // odoo-enterprise-rebuild: forwarded so Botify can later
                        // prove possession of this delegation when requesting a
                        // per-operation grant, without ever re-sending the raw
                        // identity assertion. Botify stores the key AES-encrypted
                        // and this browser never sees it again after this call.
                        delegationId: identity.delegation_id,
                        delegationKey: identity.delegation_key,
                        delegationExpiresIn: identity.delegation_expires_in,
                    }),
                }
            );
            if (!response.ok) {
                const body = await response.json().catch(() => null);
                throw new Error(body?.error?.message || `HTTP ${response.status}`);
            }
            const issued = await response.json();
            this.session = {
                token: issued.identityToken,
                expiresAt: new Date(issued.expiresAt).getTime(),
                // The delegation credential (identity.delegation_expires_in,
                // default 900s / 15min) is DELIBERATELY shorter-lived than the
                // identity session itself (identity.expires_in / issued.expiresAt,
                // default 1h) — see DELEGATION_TTL_SECONDS's comment in
                // controllers/main.py. Found live: ensureSession() used to check
                // ONLY session.expiresAt, so a conversation running past ~15
                // minutes kept the identity session "valid" while every Odoo
                // tool call silently failed server-side with "no live
                // delegation" for the rest of the hour — confusing for the user,
                // and NOT a security feature (nothing benefits from the tool
                // call failing instead of a transparent re-mint). Tracking the
                // earlier of the two expiries here restores the intended
                // behaviour: short-lived delegation, invisibly refreshed.
                delegationExpiresAt: identity.delegation_expires_in
                    ? Date.now() + identity.delegation_expires_in * 1000
                    : new Date(issued.expiresAt).getTime(),
            };
            this.state.ready = true;
        } catch (err) {
            this.state.error = `Botify rejected the sign-in: ${err.message}`;
        }
    }

    /**
     * Sessions are short-lived on purpose. When one lapses we silently mint a
     * fresh assertion — the user is still logged into Odoo, so this is
     * invisible to them, and it means a revoked Odoo account stops working
     * within one session lifetime rather than indefinitely.
     */
    async ensureSession() {
        const soonestExpiry = this.session
            ? Math.min(this.session.expiresAt, this.session.delegationExpiresAt ?? Infinity)
            : 0;
        if (this.session && Date.now() < soonestExpiry - 30_000) {
            return true;
        }
        this.state.ready = false;
        await this.connect();
        return this.state.ready;
    }

    async sendMessage() {
        const text = this.state.draft.trim();
        if (!text || this.state.sending) {
            return;
        }
        if (!(await this.ensureSession())) {
            return;
        }

        this.state.sending = true;
        this.state.messages.push({ role: "user", content: text });
        this.state.draft = "";

        try {
            const response = await fetch(`${this.baseUrl}/api/chat/${this.agentId}/message`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                    // Header rather than body: keeps the credential out of
                    // payloads that get logged or echoed back.
                    "X-Identity-Token": this.session.token,
                },
                body: JSON.stringify({
                    message: text,
                    conversationId: this.conversationId || null,
                    channel: "odoo",
                }),
            });
            if (response.status === 401) {
                // Session revoked or expired mid-turn — re-establish once.
                this.session = null;
                if (await this.ensureSession()) {
                    this.state.sending = false;
                    this.state.draft = text;
                    this.state.messages.pop();
                    return;
                }
            }
            if (!response.ok) {
                throw new Error(`HTTP ${response.status}`);
            }
            const result = await response.json();
            this.conversationId = result.conversationId;
            const reply = (result.messages || []).filter((m) => m.role === "assistant").pop();
            this.state.messages.push({
                role: "assistant",
                content: reply?.content || "(no reply)",
            });
        } catch (err) {
            this.notification.add(`Could not send the message: ${err.message}`, {
                type: "danger",
            });
            this.state.messages.push({
                role: "assistant",
                content: "Sorry — I could not reach the assistant.",
            });
        } finally {
            this.state.sending = false;
        }
    }

    revoke() {
        if (!this.session) {
            return;
        }
        const body = JSON.stringify({ token: this.session.token });
        // sendBeacon survives the page teardown that would abort a fetch.
        navigator.sendBeacon?.(
            `${this.baseUrl}/api/chat/${this.agentId}/identity/revoke`,
            new Blob([body], { type: "application/json" })
        );
        this.session = null;
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.sendMessage();
        }
    }
}

registry.category("actions").add("botify_agent.assistant", BotifyAssistant);
