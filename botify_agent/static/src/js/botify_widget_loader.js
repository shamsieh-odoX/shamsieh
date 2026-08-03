/** @odoo-module **/

import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";

/**
 * Loads the hosted Botify widget (widget.iife.js) into the Odoo backend and,
 * when identity is configured, exchanges a server-minted assertion so widget
 * API calls run as the logged-in employee.
 */
const SCRIPT_ATTR = "data-botify-widget";

const state = {
    loading: null,
    apiUrl: "",
    agentId: "",
    identityToken: null,
    identityExpiresAt: 0,
    fetchPatched: false,
    originalFetch: null,
};

function injectWidgetScript({ agentId, apiUrl, widgetScriptUrl }) {
    const existing = document.querySelector(`script[${SCRIPT_ATTR}]`);
    if (existing) {
        return existing;
    }
    const script = document.createElement("script");
    script.src = widgetScriptUrl;
    script.defer = true;
    script.setAttribute(SCRIPT_ATTR, "1");
    script.setAttribute("data-agent-id", agentId);
    script.setAttribute("data-api-url", apiUrl);
    document.body.appendChild(script);
    return script;
}

function installFetchPatch() {
    if (state.fetchPatched || typeof window.fetch !== "function") {
        return;
    }
    state.originalFetch = window.fetch.bind(window);
    window.fetch = (input, init = {}) => {
        const url = typeof input === "string" ? input : input?.url || "";
        if (state.identityToken && state.apiUrl && url.startsWith(state.apiUrl)) {
            const headers = new Headers(
                init.headers || (typeof input !== "string" ? input.headers : undefined)
            );
            if (!headers.has("X-Identity-Token")) {
                headers.set("X-Identity-Token", state.identityToken);
            }
            init = { ...init, headers };
        }
        return state.originalFetch(input, init);
    };
    state.fetchPatched = true;
}

async function exchangeIdentity(apiUrl, agentId, assertion) {
    const response = await fetch(`${apiUrl}/chat/${agentId}/identity/exchange`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ platform: "odoo", assertion }),
    });
    if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.error?.message || `HTTP ${response.status}`);
    }
    const issued = await response.json();
    state.identityToken = issued.identityToken;
    state.identityExpiresAt = new Date(issued.expiresAt).getTime();
    installFetchPatch();
}

async function refreshIdentityIfNeeded() {
    if (!state.apiUrl || !state.agentId) {
        return;
    }
    if (state.identityToken && Date.now() < state.identityExpiresAt - 30_000) {
        return;
    }
    const identity = await rpc("/botify_agent/identity", {});
    if (!identity || identity.error || !identity.assertion) {
        return;
    }
    const apiUrl = identity.api_url || state.apiUrl;
    await exchangeIdentity(apiUrl, identity.agent_id || state.agentId, identity.assertion);
}

export async function ensureBotifyWidget() {
    if (state.loading) {
        return state.loading;
    }
    state.loading = (async () => {
        const config = await rpc("/botify_agent/widget_config", {});
        if (!config || config.error) {
            return { ok: false, error: config?.error || "Botify is not configured." };
        }
        if (!config.agent_id || !config.api_url || !config.widget_script_url) {
            return { ok: false, error: "Botify widget settings are incomplete." };
        }

        state.apiUrl = config.api_url.replace(/\/+$/, "");
        state.agentId = config.agent_id;
        injectWidgetScript({
            agentId: config.agent_id,
            apiUrl: state.apiUrl,
            widgetScriptUrl: config.widget_script_url,
        });

        if (config.identity_ready) {
            try {
                await refreshIdentityIfNeeded();
            } catch (err) {
                // Widget still loads; Odoo tools stay unavailable until identity works.
                console.warn("[botify_agent] identity exchange failed:", err);
            }
        }

        return {
            ok: true,
            agentId: config.agent_id,
            apiUrl: state.apiUrl,
            identityReady: Boolean(state.identityToken),
        };
    })();

    try {
        return await state.loading;
    } finally {
        state.loading = null;
    }
}

export function revokeBotifyIdentity() {
    if (!state.identityToken || !state.apiUrl || !state.agentId) {
        return;
    }
    const body = JSON.stringify({ token: state.identityToken });
    navigator.sendBeacon?.(
        `${state.apiUrl}/chat/${state.agentId}/identity/revoke`,
        new Blob([body], { type: "application/json" })
    );
    state.identityToken = null;
    state.identityExpiresAt = 0;
}

export const botifyWidgetService = {
    dependencies: [],
    start() {
        // Floating bubble on every backend page once Settings → Botify is enabled.
        ensureBotifyWidget().catch(() => {});
        window.addEventListener("pagehide", revokeBotifyIdentity);
        return {
            ensure: ensureBotifyWidget,
            revoke: revokeBotifyIdentity,
        };
    },
};

registry.category("services").add("botify_widget", botifyWidgetService);
