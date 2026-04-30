import json

from app.db.db import execute, fetch_all, fetch_one


async def get_user_username_by_id(id: int):
    res = await fetch_one("SELECT username FROM users WHERE userID=%s", (id,))
    return res["username"]


async def create_audit_log(user_id: int | None, action: str, target_type: str | None = None, target_public_id: str | None = None, details: dict | None = None):
    details_payload = json.dumps(details or {}, ensure_ascii=True)
    await execute(
        """
        insert into audit_logs (userID, action, targetType, targetPublicID, details, createdAt)
        values (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
        """,
        (user_id, action, target_type, target_public_id, details_payload)
    )


async def get_audit_logs(limit: int = 200):
    return await fetch_all(
        """
        select
            audit_logs.logID,
            audit_logs.userID,
            users.username,
            audit_logs.action,
            audit_logs.targetType,
            audit_logs.targetPublicID,
            audit_logs.details,
            audit_logs.createdAt
        from audit_logs
        left join users on users.userID = audit_logs.userID
        order by audit_logs.createdAt desc, audit_logs.logID desc
        limit %s
        """,
        (limit,)
    )
