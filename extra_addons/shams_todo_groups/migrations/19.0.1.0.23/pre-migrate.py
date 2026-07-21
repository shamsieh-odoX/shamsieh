from .hooks import _purge_stale_todo_assets


def migrate(cr, version):
    _purge_stale_todo_assets(cr)
