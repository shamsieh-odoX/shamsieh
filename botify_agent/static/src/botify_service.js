import { browser } from '@web/core/browser/browser';
import { router, routerBus } from '@web/core/browser/router';
import { registry } from '@web/core/registry';
import { user } from '@web/core/user';

/**
 * Loads the Botify assistant for employees in the "Botify Agent user" group
 * and relays the operations Botify grants to this module's `execute` route.
 * The browser relay is a capability transport, not an authorization bypass:
 * every operation carries a grant bound to this Odoo session and runs with
 * the employee's own Odoo rights.
 */

const IDENTITY = '/botify_agent/v1/identity';
const EXECUTE = '/botify_agent/v1/execute';
const PENDING = '/botify_agent/v1/events/pending';
const ACK = '/botify_agent/v1/events/ack';
/** Events Botify has not acknowledged are leased for 60 s, then handed out again. */
const RETRY_MS = 3 * 60 * 1000;

/** JSON-RPC to this module, with the explicit CSRF header its routes require. */
async function call(route, params) {
  try {
    const response = await browser.fetch(route, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-Botify-CSRF': odoo.csrf_token },
      body: JSON.stringify({ jsonrpc: '2.0', method: 'call', id: Date.now(), params }),
    });
    const body = await response.json();
    if (body.error) {
      const expired = /SessionExpired/.test(body.error.data?.name || '');
      return {
        ok: false,
        error: {
          code: expired ? 'AUTH_EXPIRED' : 'INTERNAL',
          message: expired ? 'the Odoo session expired' : 'Odoo could not answer',
        },
      };
    }
    return body.result;
  } catch {
    return { ok: false, error: { code: 'INTERNAL', message: 'Odoo could not be reached' } };
  }
}

/**
 * Where the employee is right now. Prefer the action service's current
 * controller: menu clicks update it immediately and only then push the
 * router (debounced, and without a ROUTE_CHANGE). The router alone is for
 * back/forward and in-app `<a href>` navigations.
 */
function pageContext(actionService) {
  const route = router.current || {};
  const controller = actionService.currentController;
  const ctrl = controller?.state || {};
  const act = controller?.action || {};
  const model = ctrl.model || route.model || act.res_model || null;
  const id = ctrl.resId ?? route.resId ?? null;
  const actionKey = ctrl.action || route.action || act.tag || act.path || act.id || null;
  const name = controller?.displayName || act.display_name || act.name || null;
  const view = controller?.props?.type || route.view_type || null;
  return {
    odoo: {
      model: model || null,
      id: id ?? null,
      action: actionKey ?? null,
      ...(name ? { name: String(name).slice(0, 120) } : {}),
      ...(view ? { view: String(view).slice(0, 32) } : {}),
    },
  };
}

export const botifyAgentService = {
  dependencies: ['action', 'bus_service'],
  async start(env, { action, bus_service }) {
    const unavailable = { available: false, toggle() {} };
    if (!(await user.hasGroup('botify_agent.group_botify_user'))) {
      return unavailable;
    }
    const first = await call(IDENTITY, {});
    if (!first?.ok) {
      return unavailable;
    }
    // The loader's queue stub: calls made before widget.js runs are replayed by it.
    if (!window.Botify) {
      const stub = (...args) => {
        stub.q = stub.q || [];
        stub.q.push(args);
      };
      window.Botify = stub;
    }
    const botify = (...args) => window.Botify(...args);

    botify('identify', { assertion: first.result.assertion });
    botify('on', 'identity.expired', async () => {
      const fresh = await call(IDENTITY, {});
      if (fresh?.ok) {
        botify('identify', { assertion: fresh.result.assertion });
      }
    });
    botify('registerSystemAction', 'botify.odoo.execute', async ({ grant }) => {
      const answer = await call(EXECUTE, {
        grant_token: grant,
        context: { allowed_company_ids: user.activeCompanies.map((company) => company.id) },
      });
      const { client, ...forBotify } = answer || {};
      if (client?.action) {
        // Only this browser opens the record; Botify never sees the action.
        action.doAction(client.action);
      }
      return forBotify;
    });
    // Untrusted page data for the agent, never authority.
    const setContext = () => botify('setContext', pageContext(action));
    setContext();
    // Back/forward and internal <a href> clicks.
    routerBus.addEventListener('ROUTE_CHANGE', setContext);
    // App/menu doAction: controller is committed here; the router push is later.
    env.bus.addEventListener('ACTION_MANAGER:UI-UPDATED', setContext);

    // Notifications: Odoo keeps the events; the bus only says "look". The
    // first relay always runs so the badge shows what is still unread.
    let relaying = null;
    let initial = true;
    const relay = () => {
      relaying ??= call(PENDING, {})
        .then((pending) => {
          const events = pending?.ok ? pending.result.events : [];
          if (events.length > 0 || initial) botify('notify', events);
          initial = false;
        })
        .finally(() => {
          relaying = null;
        });
      return relaying;
    };
    botify('on', 'notifications.acked', ({ acks }) => {
      if (Array.isArray(acks) && acks.length > 0) call(ACK, { acks });
    });
    bus_service.subscribe('botify_agent/event', relay);
    bus_service.start();
    relay();
    browser.setInterval(relay, RETRY_MS);

    const script = document.createElement('script');
    script.src = first.result.loaderUrl;
    script.async = true;
    script.dataset.siteKey = first.result.siteKey;
    document.head.appendChild(script);
    return { available: true, toggle: () => botify('toggle') };
  },
};

registry.category('services').add('botify_agent', botifyAgentService);
