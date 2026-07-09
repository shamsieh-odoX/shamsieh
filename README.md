# Shamsieh — Odoo 19

Custom Odoo 19 instance for Shamsieh Technology Services. Custom business logic lives in [`extra_addons/`](extra_addons/).

- **Config:** [`debian/odoo.conf`](debian/odoo.conf)
- **Addons path:** `addons`, `extra_addons`, `odoo/addons`
- **Default URL:** http://localhost:8069

## Prerequisites

- Python 3.10+ (Odoo 19)
- PostgreSQL running locally
- A virtual environment with Odoo dependencies installed

---

## Run Odoo

### Windows

From the project root, use one of the helper scripts (expects a venv in `virtual/`):

**PowerShell**

```powershell
.\start_odoo.ps1
```

**Command Prompt**

```bat
start_odoo.bat
```

Both scripts activate `virtual\Scripts\` and start Odoo with database `odoo19`.

Pass extra Odoo arguments after the script name, for example:

```powershell
.\start_odoo.ps1 -u crm_custom_ext
```

```bat
start_odoo.bat -u crm_custom_ext
```

### macOS

There is no `Makefile` in this repo. Use Python from your Odoo venv directly.

**If you use the project `virtual/` folder** (after `source virtual/bin/activate`):

```bash
python3 odoo-bin -c debian/odoo.conf -d odoo19
```

**If your PostgreSQL user/password differ from** [`debian/odoo.conf`](debian/odoo.conf), pass them on the command line:

```bash
python3 odoo-bin -c debian/odoo.conf \
  -r <your_db_user> -w <your_db_password> \
  -d <your_database_name>
```

Replace `<your_db_user>`, `<your_db_password>`, and `<your_database_name>` with your own PostgreSQL credentials and database.

**Port already in use?** Stop the existing Odoo process:

```bash
lsof -ti :8069 | xargs kill
```

---

## Install or upgrade custom modules

Run once after pulling changes or when adding a new module.

**Windows** (from project root, venv active or via script):

```bat
python odoo-bin -c debian\odoo.conf -d odoo19 -i crm_custom_ext --stop-after-init
python odoo-bin -c debian\odoo.conf -d odoo19 -u crm_custom_ext --stop-after-init
```

**macOS** (venv active; adjust DB flags if needed):

```bash
python3 odoo-bin -c debian/odoo.conf \
  -r <your_db_user> -w <your_db_password> -d <your_database_name> \
  --stop-after-init -u crm_custom_ext
```

| Flag | Meaning |
|------|---------|
| `-i module_name` | Install (first time) |
| `-u module_name` | Upgrade (after code changes) |
| `--stop-after-init` | Apply changes and exit (no need to kill a running server) |

Then start Odoo normally and refresh the browser.

---

## Custom modules (`extra_addons/`)

### `crm_custom_ext` — CRM Custom Extensions

Shamsieh CRM: extra fields, security, country sales teams, targets, and reporting.

| Area | What it adds |
|------|----------------|
| **Lead ID** | Auto sequence `LD-YYYY-0001` (year updates automatically) |
| **New fields on `crm.lead`** | Sector, Channel (+ Other Channel text), Interest Level, contact/follow-up dates, Next Action, Demo Date, Proposal Sent Date |
| **Reused Odoo fields** | Company, contact, email, phone, city, country, Sales Owner, pipeline stage, Expected Value / Expected Revenue, notes |
| **Pipeline** | 12 Shamsieh stages (New Lead → Lost) |
| **Sales teams** | Jordan, KSA, UAE, Qatar, Other — auto-linked from lead country |
| **Targets** | `crm.team.target` — monthly/quarterly/yearly targets with achievement % |
| **Security** | **CRM Create** group — only users in this group can create leads; others read assigned leads |
| **Dashboards** | CRM → Reporting → **Shamsieh Dashboard** |
| **Search / filters** | Lead ID search, Sector/Channel/Country filters with section labels, Group By options |

**Test users** (password = login):

| Login | Role |
|-------|------|
| `crm.sales.create` | Sales + CRM Create |
| `crm.sales.readonly` | Sales read-only (no create) |
| `crm.sales.manager` | Sales Manager |

**Depends on:** `crm`, `sales_team`, `utm`, `mail`

---

### `project_custom_ext` — Project Custom Extensions

Project module customizations: security groups, progress tracking, task templates, dashboards, and sales team link on projects.

| Area | What it adds |
|------|----------------|
| **Security groups** | Project Edit Only, Project Create/Move, Project Manager |
| **Project fields** | Progress %, hours, country, sales team, task templates |
| **Task templates** | Reusable task workflows (including CRM Setup template) |
| **Dashboards** | Project → Reporting → **Project Dashboard** |
| **Closing stages** | Configurable “closing” project/task stages |

**Depends on:** `project`, `crm`, `hr_timesheet`, `sale`

---

## Database notes

[`debian/odoo.conf`](debian/odoo.conf) sets `db_user`, `db_password`, and related options. Windows start scripts use database `odoo19` by default. Create your own PostgreSQL database and user, then either update `debian/odoo.conf` or pass `-r`, `-w`, and `-d` on the command line.

---

## Upstream Odoo

This repository is based on [Odoo 19](https://www.odoo.com/documentation/19.0/). For generic install and developer docs, see the [Odoo documentation](https://www.odoo.com/documentation/19.0/).
