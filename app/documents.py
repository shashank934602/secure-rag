"""Changing who can read a document (spec 04 D7, ISS-037; ADR-0002, Invariant 2).

The document holds its audience (`allowed_roles`) and every chunk carries a copy, so search can
filter without a join. A change updates both in ONE transaction, inside the user's tenant scope:
the copies never disagree, and another tenant's document is invisible (404, not 403).
"""

import psycopg
from psycopg_pool import ConnectionPool

from app.db import borrow, tenant_scope
from app.domain import User

UPLOADER = "uploader"  # the permission needed to change a document's audience


class AclError(Exception):
    """A refused change, with the HTTP status the API should answer with."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def change_acl(
    db: psycopg.Connection | ConnectionPool, user: User, doc_id: str, roles: list[str]
) -> dict:
    """Set the roles that may read `doc_id` (a slug in the user's tenant); returns what changed."""
    if UPLOADER not in user.permissions:
        raise AclError(403, "Not allowed to change document access")
    roles = list(dict.fromkeys(roles))  # drop repeats, keep order
    if not roles:
        raise AclError(422, "allowed_roles must not be empty")

    with borrow(db) as conn, tenant_scope(conn, user.tenant_id):  # all of it, or none of it
        (tenant_roles,) = conn.execute(
            "SELECT roles FROM tenants WHERE id = %s", (user.tenant_id,)
        ).fetchone()
        unknown = [role for role in roles if role not in tenant_roles]
        if unknown:
            raise AclError(422, f"Unknown roles for this tenant: {unknown}")
        document = conn.execute(
            "UPDATE documents SET allowed_roles = %s WHERE tenant_id = %s AND slug = %s "
            "RETURNING id",
            (roles, user.tenant_id, doc_id),
        ).fetchone()
        if document is None:  # doesn't exist, or belongs to another tenant (RLS hides it)
            raise AclError(404, "Document not found")
        chunks = conn.execute(
            "UPDATE chunks SET allowed_roles = %s WHERE document_id = %s", (roles, document[0])
        )
    return {"doc_id": doc_id, "allowed_roles": roles, "chunks_updated": chunks.rowcount}
