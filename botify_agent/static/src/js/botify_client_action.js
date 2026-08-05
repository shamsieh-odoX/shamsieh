/** @odoo-module **/

import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";
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
    static props = { "*": true };

    setup() {
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
            identity = await rpc("/botify_agent/identity", {});
        } catch {
            this.state.error = "Could not reach Odoo to establish your identity.";
            return;
        }
        if (!identity || identity.error) {
            this.state.error = identity?.error || "Botify is not configured.";
            return;
        }

        // Settings may store either the API origin (https://api…) or a root
        // that already ends in /api — normalise so we never double /api.
        this.baseUrl = identity.base_url.replace(/\/+$/, "").replace(/\/api$/, "");
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
        if (this.session && Date.now() < this.session.expiresAt - 30_000) {
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
