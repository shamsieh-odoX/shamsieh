# Botify Agent — Odoo addon

Embeds a Botify AI assistant in the Odoo backend and makes it act **as the
employee using it**, not as a shared integration account.

## Why this addon exists

Odoo's External API (`/jsonrpc` `execute_kw`, or `/json/2` on Odoo 19+)
authenticates as exactly one user: whoever owns the API key. Before this addon,
every Botify tool call ran with that one user's permissions no matter which
employee was chatting — so a warehouse clerk could ask the agent for payroll and
get it, provided the integration account could see it.

There is no impersonation in the External API, and there cannot be: `execute_kw`
needs the target user's own credential. The fix has to run *inside* Odoo, where
`with_user()` exists.

## How it works

```
Employee (logged into Odoo)
   │
   │  1. client action calls /botify_agent/identity      (auth="user")
   ▼
Odoo server ── reads request.env.user ── signs a 120s assertion (HS256)
   │
   │  2. browser relays the sealed assertion
   ▼
Botify ── verifies signature, issuer, audience, expiry, single-use jti
   │      ── issues its own opaque session token
   │
   │  3. agent needs ERP data
   ▼
Botify server ── POST /botify_agent/rpc (HMAC-signed, names the uid)
   │
   ▼
Odoo ── env[model].with_user(uid).with_context(allowed_company_ids=...)
        └─ su=False ⇒ ACLs, record rules and company scope all apply
```

Two properties do the heavy lifting:

1. **The subject is never client-supplied.** `/botify_agent/identity` runs with
   `auth="user"` and reads `request.env.user`. There is no parameter that
   selects a different user — deliberately. Posting `{"uid": 1}` changes
   nothing (there is a test for exactly this).

2. **Odoo stays the authority on permissions.** `with_user()` returns an
   environment with `su=False` (see `odoo/models.py`), so access rights, record
   rules and multi-company scoping are evaluated by Odoo for that user. Botify
   copies no permissions, so none can go stale.

Company scope is self-validating: `Environment.companies` raises
`AccessError("Access to unauthorized or invalid companies.")` when
`allowed_company_ids` contains anything outside the user's own set and `su` is
false (`odoo/api.py`). That is why the addon can forward a requested company
list without auditing it first — Odoo rejects an over-broad one.

## Install

1. Copy `botify_agent/` into your Odoo addons path (or add this directory to
   `--addons-path`).
2. Restart Odoo, update the apps list, install **Botify Agent**.
3. Go to **Settings → Botify** (requires *Settings* access) and fill in:

   | Field | Value |
   |---|---|
   | Enable Botify agent | ✅ |
   | Botify API base URL | e.g. `https://api.botifyarabia.ai` |
   | Botify agent ID | UUID of the agent in Botify |
   | Botify connection ID | UUID of the **Odoo connection** record in Botify |
   | Shared secret | click **Generate new secret** |
   | Assertion lifetime | 120 seconds (30–300 allowed) |
   | Restrict to group | optional — narrows *who may start a session* |

4. In Botify, open the same Odoo connection and paste the shared secret into
   **Addon shared secret**, then set **Identity mode** to `end_user`.
5. On the agent's Odoo attachment, switch **Require verified identity** on.

Employees then get an **Assistant** menu. Anyone without a verified identity
gets no Odoo tools at all — the agent still chats, it just cannot reach the ERP.

### Reachability

`/botify_agent/rpc` must be reachable from Botify's servers. It is the only
endpoint that needs to be, and it is authenticated by HMAC rather than by a
session, so it does not need to be public to browsers.

## Security notes

**The shared secret is a high-value credential.** Holding it lets the bearer ask
this database to act as any non-superuser user. That is the same class of trust
as the API key you already store (which acts as one fixed user), but broader, so:

- It lives in `ir.config_parameter`, whose ACL grants access to `group_system`
  only — ordinary employees cannot read it through the ORM or the web client.
- It is never sent to the browser. The client action receives an *assertion*,
  never the secret.
- Botify stores it AES-encrypted (`ENCRYPTION_KEY`).
- Rotate it by generating a new one here and pasting it into Botify. Live Botify
  sessions survive (they hold their own tokens); only in-flight assertions fail,
  a window of seconds.

**What the addon refuses, independently of Botify:**

- `uid <= 1` — acting as the superuser would bypass every record rule.
- Inactive users and portal (`share`) users.
- Any method outside the allowlist, anything starting with `_`, and
  `unlink`/`sudo`/`with_user`/`with_env` specifically.
- A caller-supplied `context` (it is stripped — otherwise a caller could inject
  `active_test=False` or re-widen the company scope).
- Requests older than 300 seconds, or whose HMAC does not match. The timestamp
  is inside the MAC, so a captured request cannot be re-stamped.
- `write()` calls that touch a credential-ish field (`password`, `api_key`,
  `oauth_*`, `groups_id`, …) or a workflow field (`state`, `stage_id`) directly
  — the latter because a bare field write skips the side effects Odoo's own
  `action_confirm` / `action_post` / etc. run for that same transition
  (stock reservations, sequence numbers, validation). `create()` calls that set
  a credential-ish field.

These are duplicated on the Botify side on purpose. An `auth="none"` endpoint
has to be safe on its own terms, independent of whatever the caller claims to
have already checked.

## Tests

```bash
odoo -d <db> -i botify_agent --test-enable --stop-after-init \
     --test-tags /botify_agent
```

Covers:

- `with_user()` really yields `su=False` (if this regressed, every other
  guarantee would quietly evaporate).
- An employee scoped to company A cannot see company B's records.
- Requesting a company the user does not belong to raises `AccessError`.
- A plain employee cannot perform a manager-only write (`res.users`).
- The assertion subject is the session user, and stays so even when the request
  body tries to supply a different `uid`.
- Editing `sub` in a signed assertion breaks the signature; `alg: none` is
  refused; expired assertions are refused.
- Tampered, wrongly-signed, stale and re-stamped RPC requests are refused.

## Odoo version support

Targeted at Odoo 19 (manifest `19.0.*`); the ORM calls used are stable across
17–19. The identity route uses `type="jsonrpc"` (Odoo 19). Group membership goes
through `_user_all_groups` because Odoo 19 split `groups_id` into `group_ids` /
`all_group_ids`. The other version-sensitive call, `check_access` (18+) vs
`check_access_rights` + `check_access_rule` (17 and earlier), goes through a
shim in `controllers/main.py::_check_access`.
