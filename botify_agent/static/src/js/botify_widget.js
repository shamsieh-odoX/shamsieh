/** @odoo-module **/

/**
 * Loads the Botify floating chat widget on the Odoo backend.
 *
 * Kept as its own asset so the Assistant client action and the embed stay
 * independent — either can change without the other.
 *
 * The remote IIFE only auto-boots when it can read document.currentScript
 * (inline <script src=… data-agent-id=…>). Dynamically injected scripts leave
 * currentScript null, so we mount ChatWidget ourselves after load.
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

function guardMountedWidget(widget) {
    const host =
        widget?.shadow?.host ||
        widget?.el ||
        widget?.root ||
        document.querySelector("[data-botify-widget-host], #botify-widget, .botify-widget");
    if (host) {
        installOdooKeyGuard(host);
        return;
    }
    // Host may appear a tick after mount().
    const observer = new MutationObserver(() => {
        const shamsi = window.Shamsi;
        const lateHost = shamsi?.shadow?.host;
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
            body: JSON.stringify({ platform: identity.platform, assertion: identity.assertion }),
        });
        if (!response.ok) {
            return null;
        }
        const issued = await response.json();
        return { token: issued.identityToken, expiresAt: new Date(issued.expiresAt).getTime() };
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
        widget.setIdentityToken(next?.token || null);
        scheduleIdentityRefresh(widget, next);
    }, delay);
}

// Set synchronously, before the first `await` below. mountBotifyWidget can be
// invoked more than once (Odoo re-executing web.assets_backend scripts on
// backend navigation is routine) — window.Shamsi alone isn't a safe guard
// here because it's only assigned after `mintIdentityToken()` resolves. Any
// second invocation landing in that async gap would see window.Shamsi still
// unset and mount a duplicate, orphaned widget instance (reproduced live:
// two #chatagent-widget hosts, window.Shamsi pointing at the empty one while
// the real, visible instance — and its conversation, attachments — went
// unreferenced).
let mounting = false;

async function mountBotifyWidget() {
    const Widget = window.BotifyWidget?.ChatWidget;
    if (!Widget || window.Shamsi || mounting) {
        if (window.Shamsi) {
            guardMountedWidget(window.Shamsi);
        }
        return;
    }
    mounting = true;
    try {
        const session = await mintIdentityToken();
        if (window.Shamsi) {
            // Lost the race after all (e.g. a synchronous-path caller beat us
            // between the check above and here) — don't double-mount.
            guardMountedWidget(window.Shamsi);
            return;
        }
        const widget = new Widget({ agentId: AGENT_ID, apiUrl: API_URL, identityToken: session?.token });
        await widget.mount();
        window.Shamsi = widget;
        guardMountedWidget(widget);
        scheduleIdentityRefresh(widget, session);
    } finally {
        mounting = false;
    }
}

function injectBotifyWidget() {
    if (document.querySelector('script[data-botify-widget="1"]')) {
        void mountBotifyWidget();
        return;
    }
    const script = document.createElement("script");
    script.src = WIDGET_SRC;
    script.dataset.agentId = AGENT_ID;
    script.dataset.apiUrl = API_URL;
    script.dataset.botifyWidget = "1";
    script.onload = () => void mountBotifyWidget();
    document.head.appendChild(script);
}

injectBotifyWidget();
