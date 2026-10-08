# -*- coding: utf-8 -*-
"""Force the coded Shamsieh homepage over Website Editor COW copies."""

import logging

_logger = logging.getLogger(__name__)


def force_shamsieh_homepage(env):
    """Remove COW homepage views and point `/` pages at our template.

    Edited Odoo websites store a copy-on-write view when the homepage is
    edited in the builder. That COW replaces #wrap after our inherit, so the
    old page keeps showing until those views are cleared and website.page
    points at the coded template.
    """
    View = env['ir.ui.view'].sudo()
    cows = View.search([
        ('website_id', '!=', False),
        '|',
        ('key', '=', 'website.homepage'),
        ('inherit_id.key', '=', 'website.homepage'),
    ])
    if cows:
        _logger.info(
            'website_shamsieh: removing %s website-specific homepage view(s): %s',
            len(cows),
            cows.mapped('id'),
        )
        cows.unlink()

    our_view = env.ref('website_shamsieh.shamsieh_homepage', raise_if_not_found=False)
    if our_view:
        pages = env['website.page'].sudo().search([
            '|',
            ('url', '=', '/'),
            ('url', '=', ''),
        ])
        # Also the XML homepage_page record if present
        homepage_page = env.ref('website.homepage_page', raise_if_not_found=False)
        if homepage_page and homepage_page not in pages:
            pages |= homepage_page
        if pages:
            pages.write({
                'view_id': our_view.id,
                'is_published': True,
            })
            _logger.info(
                'website_shamsieh: pointed %s website.page record(s) to shamsieh_homepage',
                len(pages),
            )

    env.registry.clear_cache()
    try:
        env['ir.qweb'].clear_caches()
    except Exception:
        pass


def post_init_hook(env):
    force_shamsieh_homepage(env)
