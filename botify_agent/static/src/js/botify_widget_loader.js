/** @odoo-module **/

import { registry } from "@web/core/registry";
import { rpc } from "@web/core/network/rpc";

/**
 * Loads the hosted Botify widget into the Odoo backend and, when identity is
 * configured, exchanges a server-minted assertion so widget API calls run as
 * the logged-in employee.
 *
 * Odoo's command palette / home-menu search listens on window and only treats
 * light-DOM inputs as editable. Botify's composer lives in Shadow DOM, so
 * without a guard Odoo steals keystrokes into Cmd+K (and native "Ask AI"
 * picks them up). We stop those events at the host after the shadow input has
 * already handled them.
 */
const SCRIPT_ATTR = "data-botify-widget";

const state = {
    loading: null,
    apiUrl: "",
    agentId: "",
    widgetScriptUrl: "",
    identityToken: null,
    identityExpiresAt: 0,
    fetchPatched: false,
    originalFetch: null,
};

function isEditableElement(el) {
    if (!(el instanceof HTMLElement)) {
        return false;
    }
    if (el.isContentEditable) {
        return true;
    }
    const tag = el.tagName;
    if (tag !== "INPUT" && tag !== "TEXTAREA" && tag !== "SELECT") {
        return false;
    }
    if (tag === "INPUT") {
        const type = (el.type || "text").toLowerCase();
        if (type === "checkbox" || type === "radio" || type === "button" || type === "file") {
            return false;
        }
    }
    return true;
}

function eventFromBotifyEditable(ev) {
    const path = typeof ev.composedPath === "function" ? ev.composedPath() : [];
    const deepTarget = path[0];
    if (!isEditableElement(deepTarget)) {
        return false;
    }
    const shamsi = window.Shamsi;
    const shadow = shamsi?.shadow;
    if (shadow && path.includes(shadow.host)) {
        return true;
    }
    return path.some(
        (node) =>
            node instanceof Element &&
            node.shadowRoot &&
            (node.className?.toString?.().toLowerCase?.().includes("botify") ||
                node.id?.toLowerCase?.().includes("botify") ||
                node.tagName?.toLowerCase?.().includes("botify") ||
                node.className?.toString?.().toLowerCase?.().includes("chatagent") ||
                node.id?.toLowerCase?.().includes("chatagent"))
    );
}

function dismissOdooCommandPalette() {
    const paletteInput = document.querySelector(
        ".o_command_palette input, .o_command_palette_search input"
    );
    if (!paletteInput) {
        return;
    }
    document.dispatchEvent(
        new KeyboardEvent("keydown", {
            key: "Escape",
            code: "Escape",
            bubbles: true,
            cancelable: true,
        })
    );
}

function installOdooKeyGuard(host) {
    if (!host || host.dataset.botifyKeyGuard === "1") {
        return;
    }
    host.dataset.botifyKeyGuard = "1";

    const stopOdooShortcuts = (ev) => {
        if (!eventFromBotifyEditable(ev)) {
            return;
        }
        // Input already received the event inside the shadow tree; prevent
        // window/document listeners (command palette, home menu) from seeing it.
        ev.stopPropagation();
    };

    for (const type of ["keydown", "keypress", "keyup"]) {
        host.addEventListener(type, stopOdooShortcuts);
    }

    host.addEventListener(
        "focusin",
        () => {
            dismissOdooCommandPalette();
        },
        true
    );
}

function guardMountedWidget(widget) {
    const host =
        widget?.shadow?.host ||
        widget?.el ||
        widget?.root ||
        document.querySelector(
            "[data-botify-widget-host], #botify-widget, .botify-widget, #chatagent-widget-root"
        );
    if (host) {
        installOdooKeyGuard(host);
        return;
    }
    const observer = new MutationObserver(() => {
        const shamsi = window.Shamsi;
        const lateHost =
            shamsi?.shadow?.host || document.querySelector("#chatagent-widget-root");
        if (lateHost) {
            installOdooKeyGuard(lateHost);
            observer.disconnect();
        }
    });
    observer.observe(document.body, { childList: true, subtree: true });
    setTimeout(() => observer.disconnect(), 10000);
}

function mountBotifyWidget({ agentId, apiUrl }) {
    const Widget = window.BotifyWidget?.ChatWidget;
    if (window.Shamsi) {
        guardMountedWidget(window.Shamsi);
        return window.Shamsi;
    }
    if (!Widget) {
        // IIFE auto-boot may still create window.Shamsi; guard when it appears.
        guardMountedWidget(null);
        return null;
    }
    const widget = new Widget({ agentId, apiUrl });
    widget.mount().then(() => {
        window.Shamsi = widget;
        guardMountedWidget(widget);
    });
    return widget;
}

function injectWidgetScript({ agentId, apiUrl, widgetScriptUrl }) {
    const existing = document.querySelector(`script[${SCRIPT_ATTR}]`);
    if (existing) {
        mountBotifyWidget({ agentId, apiUrl });
        return existing;
    }
    const script = document.createElement("script");
    script.src = widgetScriptUrl;
    script.defer = true;
    script.setAttribute(SCRIPT_ATTR, "1");
    script.setAttribute("data-agent-id", agentId);
    script.setAttribute("data-api-url", apiUrl);
    // Dynamically injected scripts leave document.currentScript null, so the
    // IIFE may not auto-boot — mount ChatWidget ourselves after load.
    script.onload = () => mountBotifyWidget({ agentId, apiUrl });
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
        state.widgetScriptUrl = config.widget_script_url;
        injectWidgetScript({
            agentId: config.agent_id,
            apiUrl: state.apiUrl,
            widgetScriptUrl: config.widget_script_url,
        });

        if (config.identity_ready) {
            try {
                await refreshIdentityIfNeeded();
            } catch (err) {
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
        ensureBotifyWidget().catch(() => {});
        window.addEventListener("pagehide", revokeBotifyIdentity);
        return {
            ensure: ensureBotifyWidget,
            revoke: revokeBotifyIdentity,
        };
    },
};

registry.category("services").add("botify_widget", botifyWidgetService);
