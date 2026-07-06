# Part of Odoo. See LICENSE file for full copyright and licensing details.


def post_init_hook(env):
    env['res.company']._ensure_overtime_types_for_all_companies()
