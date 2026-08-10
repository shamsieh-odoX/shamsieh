#!/usr/bin/env bash
# Install Jordan payroll stack on mydb_shamsieh.
# Custom payroll addons were removed from extra_addons; this only installs
# standard/enterprise payroll modules if present.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYTHON="${PYTHON:-/Users/antonanwer/odoo-dev/odoo-19/venv/bin/python}"
ENTERPRISE_DIR="${ENTERPRISE_DIR:-/Users/antonanwer/odoo-dev/enterprise-19}"
DB="${DB:-mydb_shamsieh}"

if [[ ! -x "$PYTHON" ]]; then
  echo "Python not found: $PYTHON" >&2
  echo "Set PYTHON to your Odoo 3.10+ virtualenv python." >&2
  exit 1
fi

if [[ ! -d "$ENTERPRISE_DIR/hr_payroll" ]]; then
  echo "Enterprise addons missing at: $ENTERPRISE_DIR" >&2
  echo "Clone Odoo Enterprise 19.0 first, for example:" >&2
  echo "  git clone --depth 1 --branch 19.0 https://github.com/odoo/enterprise.git \"$ENTERPRISE_DIR\"" >&2
  exit 1
fi

cd "$ROOT"

echo "Installing payroll prerequisites on $DB..."
exec "$PYTHON" odoo-bin \
  -c debian/odoo.conf \
  -d "$DB" \
  -i hr_payroll,l10n_jo_hr_payroll \
  --stop-after-init \
  "$@"
