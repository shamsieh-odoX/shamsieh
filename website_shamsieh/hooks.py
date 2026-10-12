# -*- coding: utf-8 -*-
"""Force the coded Shamsieh homepage over Website Editor COW copies."""

import logging

_logger = logging.getLogger(__name__)


def force_shamsieh_homepage(env):
    """Remove COW/editor homepage overrides and point `/` at our template.

    Edited Odoo websites store a copy-on-write view when the homepage is
    edited in the builder (including Embed Code snippets). That replaces
    #wrap after our inherit, so a light "old" page keeps showing until
    those views are cleared and website.page points at the coded template.
    """
    View = env['ir.ui.view'].sudo()
    our_view = env.ref('website_shamsieh.shamsieh_homepage', raise_if_not_found=False)
    if not our_view:
        _logger.warning('website_shamsieh: shamsieh_homepage view missing')
        return

    # 1) Website-specific homepage views (COW of website.homepage or inherits)
    cows = View.search([
        ('website_id', '!=', False),
        '|',
        ('key', '=', 'website.homepage'),
        ('inherit_id.key', '=', 'website.homepage'),
    ])
    # 2) Any other website-specific view used as the / page that is not ours
    pages = env['website.page'].sudo().search([
        '|',
        ('url', '=', '/'),
        ('url', '=', ''),
    ])
    homepage_page = env.ref('website.homepage_page', raise_if_not_found=False)
    if homepage_page and homepage_page not in pages:
        pages |= homepage_page

    # Re-point / first so we can safely drop the old editor views.
    old_views = pages.mapped('view_id').filtered(lambda v: v and v != our_view)
    if pages:
        pages.write({
            'view_id': our_view.id,
            'is_published': True,
        })
        _logger.info(
            'website_shamsieh: pointed %s website.page record(s) to shamsieh_homepage',
            len(pages),
        )

    to_remove = (cows | old_views).filtered(
        lambda v: v
        and v != our_view
        and v.key != 'website_shamsieh.shamsieh_homepage'
        and (v.website_id or True)
    )
    # Only remove website-specific / orphaned homepage overrides, never base
    # module templates without website_id unless they were the old page view.
    to_remove = to_remove.filtered(
        lambda v: v.website_id or v in old_views
    )
    if to_remove:
        _logger.info(
            'website_shamsieh: removing %s homepage override view(s): %s',
            len(to_remove),
            to_remove.mapped('id'),
        )
        to_remove.unlink()

    env.registry.clear_cache()
    try:
        env['ir.qweb'].clear_caches()
    except Exception:
        pass


def post_init_hook(env):
    force_shamsieh_homepage(env)
