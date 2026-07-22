# -*- coding: utf-8 -*-

def migrate(cr, version):
    cr.execute("""
        UPDATE fingerprint_device
           SET auto_sync = FALSE
         WHERE api_type = 'hikvision'
           AND http_listening_enabled = TRUE
           AND auto_sync = TRUE
    """)
