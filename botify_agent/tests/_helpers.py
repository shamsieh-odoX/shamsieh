"""Shared test-only helpers.

Not imported by any production module — this file exists purely so the four
test modules do not each duplicate the same Odoo 18/19 compatibility shim.
"""


def user_group_field(env):
    """The res.users field name that accepts a (6, 0, [group_ids]) write.

    Odoo 19 split res.users.groups_id into group_ids (direct) + all_group_ids
    (direct + implied) and removed groups_id as a writable field entirely —
    creating a user with "groups_id" now raises ValueError: Invalid field.
    Odoo 18 and earlier only have groups_id. Mirrors the read-side helper
    controllers/_shared.py:user_all_groups — verified live against a real
    Odoo 19 instance (odoo:19 image), which caught this exact failure.
    """
    return "group_ids" if "group_ids" in env["res.users"]._fields else "groups_id"
