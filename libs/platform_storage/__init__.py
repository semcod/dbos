"""platform_storage — uniform entity store for every gateway/connector.

Usage
-----
    from platform_storage import get_store

    store = get_store()          # reads STORAGE_BACKEND env, default 'pg-primary'
    for t in store.list_types(): ...
    for eid in store.list_entities('article'): ...
    body, mime, updated = store.read(eid)
    store.write(eid, 'article', 'text/markdown', b'# hi')
    store.delete(eid)

Every protocol gateway (WebDAV/FTP/IMAP/POP3/SMTP) and every inbound connector
(IMAP-pull, FTP-pull, SQL-mirror, …) uses this interface. That is why they all
behave identically: the storage is abstract, the protocol is just decoration.
"""
from .base import EntityStore, EntityRef
from .factory import get_store

__all__ = ["EntityStore", "EntityRef", "get_store"]
