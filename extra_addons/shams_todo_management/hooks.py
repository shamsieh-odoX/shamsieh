# -*- coding: utf-8 -*-

def post_init_hook(env):
    env['project.task'].action_shams_deduplicate_personal_stages()
