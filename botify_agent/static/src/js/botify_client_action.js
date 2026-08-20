/** @odoo-module **/

import { registry } from "@web/core/registry";
import { rpc as rpcRequest } from "@web/core/network/rpc";
import { useService } from "@web/core/utils/hooks";
import { Component, onWillStart, onWillUnmount, useState } from "@odoo/owl";

// Voice call: hands off to the SAME production voice bundle the Botify web
// widget already ships (packages/widget's widget-voice.iife.js, sitting next
// to widget.iife.js on the Botify origin). Loading it as a classic <script>
// tag — rather than vendoring/CDN-importing the ElevenLabs SDK a second
// time here — means this addon reuses one already-tested artifact instead
// of maintaining a second copy that could drift. Idempotent + shared across
// every BotifyAssistant instance on the page, mirroring
// packages/widget/src/core/voice-loader.ts's loadVoiceSdk().
let voiceSdkPromise = null;
function loadVoiceSdk(baseUrl) {
    const existing = window.BotifyWidgetVoice;
    if (existing) {
        return Promise.resolve(existing);
    }
    if (voiceSdkPromise) {
        return voiceSdkPromise;
    }
    voiceSdkPromise = new Promise((resolve, reject) => {
        const tag = document.createElement("script");
        tag.src = `${baseUrl}/widget/widget-voice.iife.js`;
        tag.async = true;
        tag.onload = () => {
            const sdk = window.BotifyWidgetVoice;
            if (sdk) {
                resolve(sdk);
            } else {
                reject(new Error("voice-sdk-load-failed"));
            }
        };
        tag.onerror = () => reject(new Error("voice-sdk-load-failed"));
        document.head.appendChild(tag);
    }).catch((err) => {
        voiceSdkPromise = null; // let a later attempt retry instead of being stuck
        throw err;
    });
    return voiceSdkPromise;
}

const VOICE_CONNECT_TIMEOUT_MS = 15000;

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
        // Some action contexts may not bootstrap the rpc service yet.
        // Fall back to the low-level rpc helper instead of crashing setup.
        this.rpcService = null;
        try {
            this.rpcService = useService("rpc");
        } catch {
            this.rpcService = null;
        }
        this.rpc = (route, params = {}) => (
            this.rpcService ? this.rpcService(route, params) : rpcRequest(route, params)
        );
        this.notification = useService("notification");
        this.state = useState({
            ready: false,
            error: null,
            messages: [],
            draft: "",
            sending: false,
            userName: "",
            // idle | connecting | connected | disconnecting — mirrors
            // ChatWidget.ts's voice state machine, simplified for this
            // single-page component (no separate widget "controls" surface).
            voiceStatus: "idle",
            voiceError: null,
        });
        this.session = null;
        this.voiceConversation = null; // the live ElevenLabs Conversation object, once connected
        this.voiceConversationId = null; // OUR conversation id (Conversation.id in Postgres)
        this.elevenlabsConversationId = null; // ElevenLabs' own id, for the stop-call notification

        onWillStart(async () => {
            await this.connect();
        });
        onWillUnmount(() => {
            // Best-effort logout so the session dies with the tab rather than
            // waiting out its TTL.
            this.revoke();
            void this.stopVoice();
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

    // ─── Voice call ──────────────────────────────────────────────────────
    //
    // Was previously impossible for an end_user-identityMode Odoo connection:
    // the Odoo-side identity exchange above (connect()) only ever fed a
    // text-only fetch() flow, so a voice call started from
    // packages/widget's ChatWidget.ts (the only surface with voice) never
    // carried an Odoo identity, and every Odoo tool was silently withheld
    // for the whole call (see services/odoo/agentTools.ts's
    // resolveExecutionIdentity — end_user mode returns null without a
    // verified identity). The backend/widget-route plumbing to carry an
    // identity into a voice call already existed and works correctly
    // (GET /api/widget/:agentId/elevenlabs/signed-url already accepts
    // X-Identity-Token exactly like the chat path); this component just
    // never called it. Reuses this.session.token — the same identity this
    // component already established for text chat — so the assistant sees
    // exactly the same Odoo permissions on a call as in the chat above.

    isVoiceActive() {
        return this.state.voiceStatus === "connecting" || this.state.voiceStatus === "connected";
    }

    async toggleVoice() {
        if (this.isVoiceActive()) {
            await this.stopVoice();
        } else {
            await this.startVoice();
        }
    }

    async startVoice() {
        if (this.state.voiceStatus !== "idle") {
            return;
        }
        if (!(await this.ensureSession())) {
            return;
        }
        this.state.voiceError = null;
        this.state.voiceStatus = "connecting";

        // Ask for the mic FIRST — a rejected/blocked prompt should fail fast,
        // before minting server-side credentials for a call that can't open.
        try {
            if (navigator.mediaDevices?.getUserMedia) {
                const mic = await navigator.mediaDevices.getUserMedia({ audio: true });
                mic.getTracks().forEach((track) => track.stop());
            }
        } catch {
            this.state.voiceStatus = "idle";
            this.state.voiceError = "Microphone access is required for a voice call.";
            return;
        }

        let credentials;
        try {
            const res = await fetch(`${this.baseUrl}/api/widget/${this.agentId}/elevenlabs/signed-url`, {
                // Same identity contract as sendMessage() above — proves this
                // call belongs to the Odoo user this.session was minted for.
                headers: { "X-Identity-Token": this.session.token },
            });
            if (!res.ok) {
                throw new Error(`HTTP ${res.status}`);
            }
            credentials = await res.json();
            if (!credentials.conversationToken && !credentials.signedUrl) {
                throw new Error("missing-credentials");
            }
        } catch (err) {
            this.state.voiceStatus = "idle";
            this.state.voiceError = `Could not start the call: ${err.message}`;
            return;
        }
        this.voiceConversationId = credentials.conversationId || null;

        let sdk;
        try {
            sdk = await loadVoiceSdk(this.baseUrl);
        } catch {
            this.state.voiceStatus = "idle";
            this.state.voiceError = "Could not load the voice component.";
            this.notifyVoiceStop(); // credentials were minted — close the placeholder conversation
            return;
        }

        try {
            let convo;
            if (credentials.conversationToken) {
                try {
                    convo = await this.connectVoiceOnce(sdk, {
                        conversationToken: credentials.conversationToken,
                        connectionType: "webrtc",
                    });
                } catch (webrtcErr) {
                    if (!credentials.signedUrl) {
                        throw webrtcErr;
                    }
                    // WebRTC is commonly blocked on corporate networks — exactly
                    // where an Odoo-embedded assistant is likely to run.
                    convo = await this.connectVoiceOnce(sdk, {
                        signedUrl: credentials.signedUrl,
                        connectionType: "websocket",
                    });
                }
            } else {
                convo = await this.connectVoiceOnce(sdk, {
                    signedUrl: credentials.signedUrl,
                    connectionType: "websocket",
                });
            }
            this.voiceConversation = convo;
            this.state.voiceStatus = "connected";
        } catch (err) {
            this.state.voiceStatus = "idle";
            this.state.voiceError = `Could not start the call: ${err.message}`;
            this.notifyVoiceStop();
        }
    }

    /** One connection attempt over one transport. Resolves with a live,
     * connected Conversation, or rejects and tears itself down — mirrors
     * ChatWidget.ts's connectVoiceOnce(). */
    connectVoiceOnce(sdk, transport) {
        return new Promise((resolve, reject) => {
            let convo = null; // set once startSession()'s own promise resolves
            let connected = false; // set once onConnect fires
            let settled = false;

            // startSession() can resolve AFTER onConnect fires (or before) —
            // only settle once BOTH have happened, exactly like
            // ChatWidget.ts's succeed(). Resolving from onConnect alone risks
            // resolving with a still-null `convo`.
            const succeed = () => {
                if (settled || !connected || !convo) {
                    return;
                }
                settled = true;
                clearTimeout(timer);
                resolve(convo);
            };

            const timer = setTimeout(() => {
                if (settled) {
                    return;
                }
                settled = true;
                const late = convo;
                convo = null;
                void late?.endSession().catch(() => {});
                reject(new Error("timeout"));
            }, VOICE_CONNECT_TIMEOUT_MS);

            sdk.Conversation.startSession({
                ...transport,
                // Lets the agent's tool loop post this turn's replies back
                // into THIS conversation row instead of opening a second one
                // server-side — same trick the web widget uses.
                ...(this.voiceConversationId
                    ? { dynamicVariables: { app_conversation_id: this.voiceConversationId } }
                    : {}),
                onConnect: () => {
                    if (settled) {
                        return;
                    }
                    connected = true;
                    succeed();
                },
                onDisconnect: () => {
                    this.voiceConversation = null;
                    if (connected) {
                        this.state.voiceStatus = "idle";
                        this.notifyVoiceStop();
                    } else if (!settled) {
                        settled = true;
                        clearTimeout(timer);
                        reject(new Error("disconnected"));
                    }
                },
                onError: (message) => {
                    if (connected) {
                        this.voiceConversation = null;
                        this.state.voiceStatus = "idle";
                        this.state.voiceError = message || "Voice call error.";
                        this.notifyVoiceStop();
                    } else if (!settled) {
                        settled = true;
                        clearTimeout(timer);
                        reject(new Error(message || "voice-error"));
                    }
                },
            })
                .then((c) => {
                    convo = c;
                    if (settled) {
                        // Lost the race to the timeout/error above — a late
                        // success must not resurrect an attempt already failed.
                        void convo.endSession().catch(() => {});
                        convo = null;
                        return;
                    }
                    succeed(); // resolves now if onConnect already fired; otherwise waits for it
                })
                .catch((err) => {
                    if (!settled) {
                        settled = true;
                        clearTimeout(timer);
                        reject(err);
                    }
                });
        });
    }

    async stopVoice() {
        if (this.state.voiceStatus === "idle") {
            return;
        }
        this.state.voiceStatus = "disconnecting";
        try {
            await this.voiceConversation?.endSession();
        } catch {
            /* best-effort */
        } finally {
            this.voiceConversation = null;
            this.state.voiceStatus = "idle";
            // Idempotent — guarantees the server-side conversation is closed
            // even when hanging up mid-connect, before a live session existed.
            this.notifyVoiceStop();
        }
    }

    /** Closes the server-side voice conversation so it isn't left "active"
     * until the idle sweep bills it as phantom minutes. Mirrors
     * ChatWidget.ts's notifyVoiceStop() exactly. */
    notifyVoiceStop() {
        if (!this.voiceConversationId) {
            return;
        }
        const conversationId = this.voiceConversationId;
        const elevenlabsConversationId = this.elevenlabsConversationId;
        this.voiceConversationId = null;
        this.elevenlabsConversationId = null;
        fetch(`${this.baseUrl}/api/widget/${this.agentId}/elevenlabs/stop`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ conversationId, elevenlabsConversationId }),
        }).catch(() => {});
    }

    onKeydown(ev) {
        if (ev.key === "Enter" && !ev.shiftKey) {
            ev.preventDefault();
            this.sendMessage();
        }
    }
}

registry.category("actions").add("botify_agent.assistant", BotifyAssistant);
