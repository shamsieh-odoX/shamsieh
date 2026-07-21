# Tests are loaded explicitly with --test-tags hr_attendance_custom_ext.
# They are excluded from the default Odoo.sh suite to avoid OOM / KILLED builds
# (HttpCase + many TransactionCase files exceed shared runner limits).
