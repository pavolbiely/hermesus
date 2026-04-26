"""User message mutation helpers for the web chat API."""

from __future__ import annotations

from collections.abc import Callable

from fastapi import HTTPException, status
from hermes_state import SessionDB


def numeric_message_id_or_404(message_id: str) -> int:
    try:
        return int(message_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found") from exc


def edit_user_message(
    db: SessionDB,
    session_id: str,
    message_id: str,
    content: str,
    *,
    delete_git_changes_after_message: Callable[[SessionDB, str, int], None],
) -> None:
    numeric_message_id = numeric_message_id_or_404(message_id)

    def _do(conn):
        row = conn.execute(
            "SELECT * FROM messages WHERE id = ? AND session_id = ?",
            (numeric_message_id, session_id),
        ).fetchone()
        if not row:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")
        if row["role"] != "user":
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only user messages can be edited.")

        conn.execute(
            "UPDATE messages SET content = ? WHERE id = ? AND session_id = ?",
            (content, numeric_message_id, session_id),
        )
        conn.execute(
            "DELETE FROM messages WHERE session_id = ? AND id > ?",
            (session_id, numeric_message_id),
        )
        counts = conn.execute(
            """
            SELECT
                COUNT(*) AS message_count,
                SUM(CASE WHEN role = 'tool' OR tool_calls IS NOT NULL THEN 1 ELSE 0 END) AS tool_call_count
            FROM messages
            WHERE session_id = ?
            """,
            (session_id,),
        ).fetchone()
        conn.execute(
            "UPDATE sessions SET message_count = ?, tool_call_count = ? WHERE id = ?",
            (counts["message_count"] or 0, counts["tool_call_count"] or 0, session_id),
        )

    db._execute_write(_do)
    delete_git_changes_after_message(db, session_id, numeric_message_id)


def validate_edited_message_continuation(db: SessionDB, session_id: str, message_id: str) -> None:
    numeric_message_id = numeric_message_id_or_404(message_id)

    messages = db.get_messages(session_id)
    if not messages:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Message not found")

    latest = messages[-1]
    if latest.get("id") != numeric_message_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Edited message must be the latest message in the chat.")
    if latest.get("role") != "user":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only user messages can be edited.")
