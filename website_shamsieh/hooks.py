# -*- coding: utf-8 -*-
"""Ensure the published homepage picks up the Shamsieh template after install."""

import logging

_logger = logging.getLogger(__name__)


def post_init_hook(env):
    """Reset website-specific homepage copies so the module inherit is visible.

    Edited Odoo websites store a COW view of homepage. Those copies can hide
    new xpath inherits until the page is reset to the module template.
    """
    Homepage = env.ref('website.homepage', raise_if_not_found=False)
    if not Homepage:
        return
    # Delete website-specific extensions of homepage that only hold old editor content.
    cow_views = env['ir.ui.view'].sudo().search([
        ('key', '=', 'website.homepage'),
        ('website_id', '!=', False),
    ])
    if cow_views:
        _logger.info(
            'website_shamsieh: clearing %s website-specific homepage view(s)',
            len(cow_views),
        )
        cow_views.unlink()
