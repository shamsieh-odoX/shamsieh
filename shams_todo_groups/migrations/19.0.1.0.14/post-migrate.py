# -*- coding: utf-8 -*-


def migrate(cr, version):
    """Normalize legacy priority keys to Odoo priority-widget values."""
    cr.execute(
        """
        UPDATE shams_todo_task
           SET priority = CASE priority
                WHEN 'low' THEN '0'
                WHEN 'normal' THEN '1'
                WHEN 'high' THEN '2'
                WHEN 'urgent' THEN '3'
                ELSE priority
           END
         WHERE priority IN ('low', 'normal', 'high', 'urgent')
        """
    )

    # Creator was previously added as member only — promote members of
    # groups that have no managers so they can keep editing those groups.
    cr.execute(
        """
        INSERT INTO shams_todo_group_manager_rel (group_id, user_id)
        SELECT m.group_id, m.user_id
          FROM shams_todo_group_member_rel m
         WHERE NOT EXISTS (
                SELECT 1
                  FROM shams_todo_group_manager_rel mgr
                 WHERE mgr.group_id = m.group_id
             )
           AND NOT EXISTS (
                SELECT 1
                  FROM shams_todo_group_manager_rel mgr2
                 WHERE mgr2.group_id = m.group_id
                   AND mgr2.user_id = m.user_id
             )
        """
    )

    # Record rules are noupdate=1; force manager read access.
    cr.execute(
        """
        UPDATE ir_rule
           SET perm_read = TRUE
         WHERE id IN (
                SELECT res_id
                  FROM ir_model_data
                 WHERE module = 'shams_todo_groups'
                   AND name = 'shams_todo_group_rule_manager_write'
             )
        """
    )
