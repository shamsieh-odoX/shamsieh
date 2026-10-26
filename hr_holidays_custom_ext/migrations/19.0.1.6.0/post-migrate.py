# Part of Odoo. See LICENSE file for full copyright and licensing details.

import logging

_logger = logging.getLogger(__name__)


def migrate(cr, version):
    """Org-chart two-step approval: no data rewrite required.

    After upgrade, set Settings → Time Off General Manager (e.g. Basem) and keep
    leave types on Approval = "By Employee's Approver and Time Off Officer".
    """
    _logger.info(
        'hr_holidays_custom_ext 19.0.1.6.0: org-chart approval (manager→HR / HR→GM) active'
    )
