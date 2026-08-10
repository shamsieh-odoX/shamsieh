/** @odoo-module **/

/**
 * Loads the Botify floating chat widget on the Odoo backend.
 *
 * Kept as its own asset so the Assistant client action and the embed stay
 * independent — either can change without the other.
 *
 * Do NOT set data-agent-id / data-api-url on the injected script. The remote
 * IIFE auto-boots when it can read those attrs from document.currentScript
 * (which Chrome sets even for dynamically appended scripts). We mount
 * ChatWidget ourselves after load so we can pass the Odoo identity token.
 *
 * Odoo's command palette / home-menu search listens on window and only treats
 * light-DOM inputs as editable. Botify's composer lives in Shadow DOM, so
 * Odoo steals keystrokes into Cmd+K. We stop those events at the host after
 * the shadow input has already handled them.
 */
const WIDGET_SRC = "https://botifyarabia.ai/widget/widget.iife.js";
const AGENT_ID = "34c7eb31-7a92-469c-b6b9-4501f5e27a28";
const API_URL = "https://botifyarabia.ai/api";

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
    // Fallback if the widget exposes no .shadow yet: any open shadow host in path.
    return path.some(
        (node) =>
            node instanceof Element &&
            node.shadowRoot &&
            (node.className?.toString?.().toLowerCase?.().includes("botify") ||
                node.id?.toLowerCase?.().includes("botify") ||
                node.tagName?.toLowerCase?.().includes("botify"))
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

function getWidgetHost(widget) {
    return (
        widget?.shadow?.host ||
        widget?.el ||
        widget?.root ||
        document.getElementById("chatagent-widget") ||
        document.querySelector("[data-botify-widget-host], #botify-widget, .botify-widget")
    );
}

function guardMountedWidget(widget) {
    const host = getWidgetHost(widget);
    if (host) {
        installOdooKeyGuard(host);
        return;
    }
    // Host may appear a tick after mount().
    const observer = new MutationObserver(() => {
        const shamsi = window.Shamsi;
        const lateHost = getWidgetHost(shamsi);
        if (lateHost) {
            installOdooKeyGuard(lateHost);
            observer.disconnect();
        }
    });
    observer.observe(document.body, { childList: true, subtree: true });
    setTimeout(() => observer.disconnect(), 10000);
}

/**
 * Identity: mint an assertion from Odoo (same-origin, session cookie already
 * proves who's logged in) and exchange it for a Botify session token, so the
 * floating widget is the same verified caller as the Assistant page — not
 * just a plain anonymous embed. Best-effort: any failure here (addon
 * disabled, portal user, network hiccup) leaves the widget usable, just
 * without tools that require a verified identity.
 */
async function mintIdentityToken() {
    let identity;
    try {
        const res = await fetch("/botify_agent/identity", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ jsonrpc: "2.0", method: "call", params: {} }),
        });
        const body = await res.json();
        identity = body.result;
    } catch {
        return null;
    }
    if (!identity || identity.error) {
        return null;
    }
    try {
        const baseUrl = (identity.base_url || API_URL.replace(/\/api\/?$/, ""))
            .replace(/\/+$/, "")
            .replace(/\/api$/, "");
        const response = await fetch(`${baseUrl}/api/chat/${identity.agent_id}/identity/exchange`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                platform: identity.platform,
                assertion: identity.assertion,
                // Protocol v2 (odoo-enterprise-rebuild): forwarded so Botify can
                // later prove possession of this delegation when requesting a
                // per-operation grant, without ever re-sending the raw identity
                // assertion. Botify stores the key AES-encrypted and this browser
                // never sees it again after this call. Without these three
                // fields the exchange still succeeds (they are optional on the
                // backend for addons without delegation support) but every
                // Odoo tool call then fails closed with "no live delegation" —
                // found live on this exact widget after upgrading the addon to
                // protocol v2 without also updating this file.
                delegationId: identity.delegation_id,
                delegationKey: identity.delegation_key,
                delegationExpiresIn: identity.delegation_expires_in,
            }),
        });
        if (!response.ok) {
            return null;
        }
        const issued = await response.json();
        // The delegation credential (identity.delegation_expires_in, default
        // 900s/15min) is DELIBERATELY shorter-lived than the identity session
        // itself (issued.expiresAt, default 1h) — see DELEGATION_TTL_SECONDS's
        // comment in controllers/main.py. Found live: this used to return only
        // the identity's (longer) expiry, so scheduleIdentityRefresh below kept
        // scheduling refreshes ~1h apart while the delegation silently expired
        // after 15min — every Odoo tool call then failed with "no live
        // delegation" for the remaining ~45min of every hour, invisible to this
        // refresh logic. Returning the EARLIER of the two expiries restores the
        // intended behaviour: short-lived delegation, invisibly refreshed.
        const delegationExpiresAt = identity.delegation_expires_in
            ? Date.now() + identity.delegation_expires_in * 1000
            : new Date(issued.expiresAt).getTime();
        return {
            token: issued.identityToken,
            expiresAt: Math.min(new Date(issued.expiresAt).getTime(), delegationExpiresAt),
        };
    } catch {
        return null;
    }
}

let identityRefreshTimer = null;

/** Re-mint ~30s before the session expires so the widget never hits a stale token mid-chat. */
function scheduleIdentityRefresh(widget, session) {
    if (identityRefreshTimer) {
        clearTimeout(identityRefreshTimer);
    }
    if (!session) {
        return;
    }
    const delay = Math.max(session.expiresAt - Date.now() - 30_000, 5_000);
    identityRefreshTimer = setTimeout(async () => {
        const next = await mintIdentityToken();
        widget.setIdentityToken?.(next?.token || null);
        scheduleIdentityRefresh(widget, next);
    }, delay);
}

async function attachIdentity(widget) {
    const session = await mintIdentityToken();
    if (session?.token && typeof widget.setIdentityToken === "function") {
        widget.setIdentityToken(session.token);
    }
    scheduleIdentityRefresh(widget, session);
    return session;
}

/**
 * Singleton mount. Use window-level locks (not module locals) because Odoo can
 * re-evaluate this asset on backend navigation, which resets module state while
 * a previous mount is still awaiting identity minting.
 */
async function mountBotifyWidget() {
    const Widget = window.BotifyWidget?.ChatWidget;
    if (!Widget) {
        return;
    }
    if (window.Shamsi) {
        guardMountedWidget(window.Shamsi);
        return;
    }
    if (document.getElementById("chatagent-widget")) {
        return;
    }
    if (window.__botifyMounting) {
        return;
    }
    window.__botifyMounting = true;
    try {
        if (window.Shamsi || document.getElementById("chatagent-widget")) {
            if (window.Shamsi) {
                guardMountedWidget(window.Shamsi);
            }
            return;
        }
        const session = await mintIdentityToken();
        if (window.Shamsi || document.getElementById("chatagent-widget")) {
            if (window.Shamsi) {
                guardMountedWidget(window.Shamsi);
                await attachIdentity(window.Shamsi);
            }
            return;
        }
        const widget = new Widget({
            agentId: AGENT_ID,
            apiUrl: API_URL,
            identityToken: session?.token,
        });
        await widget.mount();
        window.Shamsi = widget;
        guardMountedWidget(widget);
        scheduleIdentityRefresh(widget, session);
    } finally {
        window.__botifyMounting = false;
    }
}

function injectBotifyWidget() {
    if (document.querySelector('script[data-botify-widget="1"]')) {
        void mountBotifyWidget();
        return;
    }
    const script = document.createElement("script");
    script.src = WIDGET_SRC;
    // Loader marker only — do not set data-agent-id / data-api-url or the IIFE
    // auto-boots a second bubble alongside our manual mount.
    script.dataset.botifyWidget = "1";
    script.onload = () => void mountBotifyWidget();
    document.head.appendChild(script);
}

injectBotifyWidget();
