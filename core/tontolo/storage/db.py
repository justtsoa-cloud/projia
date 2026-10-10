"""Base SQLite (mode WAL) : historique canonique, quotas, dépenses, jobs médias.

Les messages sont stockés au format OpenAI canonique (indépendant du
fournisseur) ; chaque message garde le modèle qui l'a produit. Les médias
restent sur disque : la base ne contient que leur chemin.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import aiosqlite

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    summary TEXT,
    summary_upto INTEGER NOT NULL DEFAULT 0,
    deleted INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_conv_updated ON conversations(updated_at DESC);

CREATE TABLE IF NOT EXISTS messages (
    uid TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    seq INTEGER NOT NULL,
    role TEXT NOT NULL,
    body TEXT NOT NULL,
    model TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_msg_conv ON messages(conversation_id, seq);
CREATE INDEX IF NOT EXISTS idx_msg_updated ON messages(updated_at);

CREATE TABLE IF NOT EXISTS preferences (
    scope TEXT NOT NULL,
    scope_key TEXT NOT NULL,
    model TEXT NOT NULL,
    strict INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (scope, scope_key)
);

CREATE TABLE IF NOT EXISTS quota_state (
    key TEXT PRIMARY KEY,
    data TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS reliability (
    key TEXT PRIMARY KEY,
    ok REAL NOT NULL,
    total REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS catalog_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    kind TEXT NOT NULL,
    model_id TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT '{}',
    seen INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_changes_ts ON catalog_changes(ts DESC);

CREATE TABLE IF NOT EXISTS spend (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts REAL NOT NULL,
    model TEXT NOT NULL,
    tokens_in INTEGER NOT NULL,
    tokens_out INTEGER NOT NULL,
    cost_usd REAL NOT NULL,
    conversation_id TEXT
);
CREATE INDEX IF NOT EXISTS idx_spend_ts ON spend(ts);

CREATE TABLE IF NOT EXISTS media_jobs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    status TEXT NOT NULL,
    model TEXT,
    prompt TEXT NOT NULL DEFAULT '',
    params TEXT NOT NULL DEFAULT '{}',
    result_path TEXT,
    error TEXT,
    conversation_id TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_jobs_created ON media_jobs(created_at DESC);

CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""


def now() -> float:
    return time.time()


class Database:
    """Accès asynchrone à la base. Une seule connexion, sérialisée par aiosqlite."""

    def __init__(self, path: Path | str) -> None:
        self.path = str(path)
        self._conn: aiosqlite.Connection | None = None

    async def open(self) -> Database:
        self._conn = await aiosqlite.connect(self.path)
        self._conn.row_factory = aiosqlite.Row
        if self.path != ":memory:":
            await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA synchronous=NORMAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._conn.executescript(SCHEMA)
        await self._conn.execute(
            "INSERT OR IGNORE INTO kv(key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        await self._conn.commit()
        return self

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Base non ouverte")
        return self._conn

    async def _fetchall(self, sql: str, args: Iterable[Any] = ()) -> list[aiosqlite.Row]:
        async with self.conn.execute(sql, tuple(args)) as cur:
            return list(await cur.fetchall())

    async def _fetchone(self, sql: str, args: Iterable[Any] = ()) -> aiosqlite.Row | None:
        async with self.conn.execute(sql, tuple(args)) as cur:
            return await cur.fetchone()

    # --- Conversations -------------------------------------------------

    async def create_conversation(self, title: str = "", conv_id: str | None = None) -> str:
        cid = conv_id or uuid.uuid4().hex
        ts = now()
        await self.conn.execute(
            "INSERT INTO conversations(id, title, created_at, updated_at) VALUES (?, ?, ?, ?)",
            (cid, title, ts, ts),
        )
        await self.conn.commit()
        return cid

    async def conversation_exists(self, cid: str) -> bool:
        row = await self._fetchone(
            "SELECT 1 FROM conversations WHERE id = ? AND deleted = 0", (cid,)
        )
        return row is not None

    async def list_conversations(
        self, limit: int = 50, offset: int = 0, query: str | None = None
    ) -> list[dict[str, Any]]:
        if query:
            rows = await self._fetchall(
                """SELECT DISTINCT c.id, c.title, c.created_at, c.updated_at
                   FROM conversations c LEFT JOIN messages m ON m.conversation_id = c.id
                   WHERE c.deleted = 0 AND (c.title LIKE ? OR m.body LIKE ?)
                   ORDER BY c.updated_at DESC LIMIT ? OFFSET ?""",
                (f"%{query}%", f"%{query}%", limit, offset),
            )
        else:
            rows = await self._fetchall(
                """SELECT id, title, created_at, updated_at FROM conversations
                   WHERE deleted = 0 ORDER BY updated_at DESC LIMIT ? OFFSET ?""",
                (limit, offset),
            )
        return [dict(r) for r in rows]

    async def rename_conversation(self, cid: str, title: str) -> None:
        await self.conn.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?", (title, now(), cid)
        )
        await self.conn.commit()

    async def delete_conversation(self, cid: str) -> None:
        # Suppression logique : propagée par la synchronisation.
        await self.conn.execute(
            "UPDATE conversations SET deleted = 1, updated_at = ? WHERE id = ?", (now(), cid)
        )
        await self.conn.commit()

    async def set_summary(self, cid: str, summary: str, upto_seq: int) -> None:
        await self.conn.execute(
            "UPDATE conversations SET summary = ?, summary_upto = ? WHERE id = ?",
            (summary, upto_seq, cid),
        )
        await self.conn.commit()

    async def get_summary(self, cid: str) -> tuple[str | None, int]:
        row = await self._fetchone(
            "SELECT summary, summary_upto FROM conversations WHERE id = ?", (cid,)
        )
        if row is None:
            return None, 0
        return row["summary"], int(row["summary_upto"])

    # --- Messages ------------------------------------------------------

    async def add_message(
        self, cid: str, message: dict[str, Any], model: str | None = None
    ) -> dict[str, Any]:
        row = await self._fetchone(
            "SELECT COALESCE(MAX(seq), 0) AS s FROM messages WHERE conversation_id = ?", (cid,)
        )
        seq = int(row["s"]) + 1 if row else 1
        uid = uuid.uuid4().hex
        ts = now()
        await self.conn.execute(
            """INSERT INTO messages(uid, conversation_id, seq, role, body, model, created_at,
               updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (uid, cid, seq, message["role"], json.dumps(message, ensure_ascii=False), model, ts,
             ts),
        )
        await self.conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (ts, cid))
        await self.conn.commit()
        return {"uid": uid, "seq": seq, "model": model, "created_at": ts, **message}

    async def get_messages(
        self, cid: str, after_seq: int = 0, limit: int | None = None
    ) -> list[dict[str, Any]]:
        sql = "SELECT uid, seq, body, model, created_at FROM messages WHERE conversation_id = ? "
        sql += "AND seq > ? ORDER BY seq"
        args: list[Any] = [cid, after_seq]
        if limit:
            sql += " LIMIT ?"
            args.append(limit)
        rows = await self._fetchall(sql, args)
        out = []
        for r in rows:
            msg = json.loads(r["body"])
            msg["_meta"] = {
                "uid": r["uid"], "seq": r["seq"], "model": r["model"],
                "created_at": r["created_at"],
            }
            out.append(msg)
        return out

    # --- Préférences de modèle (F8) -----------------------------------

    async def set_preference(
        self, scope: str, scope_key: str, model: str | None, strict: bool = False
    ) -> None:
        if model is None:
            await self.conn.execute(
                "DELETE FROM preferences WHERE scope = ? AND scope_key = ?", (scope, scope_key)
            )
        else:
            await self.conn.execute(
                """INSERT INTO preferences(scope, scope_key, model, strict) VALUES (?, ?, ?, ?)
                   ON CONFLICT(scope, scope_key) DO UPDATE SET model = excluded.model,
                   strict = excluded.strict""",
                (scope, scope_key, model, int(strict)),
            )
        await self.conn.commit()

    async def get_preferences(self) -> list[dict[str, Any]]:
        rows = await self._fetchall("SELECT scope, scope_key, model, strict FROM preferences")
        return [dict(r) | {"strict": bool(r["strict"])} for r in rows]

    # --- Quotas et fiabilité -------------------------------------------

    async def save_quota(self, key: str, data: dict[str, Any]) -> None:
        await self.conn.execute(
            "INSERT INTO quota_state(key, data) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET data = excluded.data",
            (key, json.dumps(data)),
        )
        await self.conn.commit()

    async def load_quotas(self) -> dict[str, dict[str, Any]]:
        rows = await self._fetchall("SELECT key, data FROM quota_state")
        return {r["key"]: json.loads(r["data"]) for r in rows}

    async def save_reliability(self, key: str, ok: float, total: float) -> None:
        await self.conn.execute(
            "INSERT INTO reliability(key, ok, total, updated_at) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET ok = excluded.ok, total = excluded.total, "
            "updated_at = excluded.updated_at",
            (key, ok, total, now()),
        )
        await self.conn.commit()

    async def load_reliability(self) -> dict[str, tuple[float, float]]:
        rows = await self._fetchall("SELECT key, ok, total FROM reliability")
        return {r["key"]: (float(r["ok"]), float(r["total"])) for r in rows}

    # --- Fil « Nouveautés » --------------------------------------------

    async def add_changes(self, changes: list[dict[str, Any]]) -> None:
        if not changes:
            return
        ts = now()
        await self.conn.executemany(
            "INSERT INTO catalog_changes(ts, kind, model_id, detail) VALUES (?, ?, ?, ?)",
            [(c.get("ts", ts), c["kind"], c["model_id"],
              json.dumps(c.get("detail", {}), ensure_ascii=False)) for c in changes],
        )
        await self.conn.commit()

    async def list_changes(self, limit: int = 100) -> list[dict[str, Any]]:
        rows = await self._fetchall(
            "SELECT id, ts, kind, model_id, detail, seen FROM catalog_changes "
            "ORDER BY ts DESC, id DESC LIMIT ?",
            (limit,),
        )
        return [dict(r) | {"detail": json.loads(r["detail"]), "seen": bool(r["seen"])}
                for r in rows]

    async def mark_changes_seen(self) -> None:
        await self.conn.execute("UPDATE catalog_changes SET seen = 1 WHERE seen = 0")
        await self.conn.commit()

    # --- Dépenses (F4) -------------------------------------------------

    async def add_spend(
        self, model: str, tokens_in: int, tokens_out: int, cost: float, cid: str | None
    ) -> None:
        await self.conn.execute(
            "INSERT INTO spend(ts, model, tokens_in, tokens_out, cost_usd, conversation_id) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (now(), model, tokens_in, tokens_out, cost, cid),
        )
        await self.conn.commit()

    async def spend_since(self, since_ts: float) -> float:
        row = await self._fetchone(
            "SELECT COALESCE(SUM(cost_usd), 0) AS s FROM spend WHERE ts >= ?", (since_ts,)
        )
        return float(row["s"]) if row else 0.0

    async def list_spend(self, limit: int = 200) -> list[dict[str, Any]]:
        rows = await self._fetchall("SELECT * FROM spend ORDER BY ts DESC LIMIT ?", (limit,))
        return [dict(r) for r in rows]

    # --- Jobs médias ---------------------------------------------------

    async def upsert_job(self, job: dict[str, Any]) -> None:
        ts = now()
        await self.conn.execute(
            """INSERT INTO media_jobs(id, kind, status, model, prompt, params, result_path, error,
               conversation_id, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(id) DO UPDATE SET status = excluded.status, model = excluded.model,
               result_path = excluded.result_path, error = excluded.error,
               params = excluded.params, updated_at = excluded.updated_at""",
            (job["id"], job["kind"], job["status"], job.get("model"), job.get("prompt", ""),
             json.dumps(job.get("params", {}), ensure_ascii=False), job.get("result_path"),
             job.get("error"), job.get("conversation_id"), job.get("created_at", ts), ts),
        )
        await self.conn.commit()

    async def get_job(self, job_id: str) -> dict[str, Any] | None:
        row = await self._fetchone("SELECT * FROM media_jobs WHERE id = ?", (job_id,))
        return _job_row(row) if row else None

    async def list_jobs(
        self, limit: int = 100, status: str | None = None, kind: str | None = None
    ) -> list[dict[str, Any]]:
        sql = "SELECT * FROM media_jobs WHERE 1=1"
        args: list[Any] = []
        if status:
            sql += " AND status = ?"
            args.append(status)
        if kind:
            sql += " AND kind = ?"
            args.append(kind)
        sql += " ORDER BY created_at DESC LIMIT ?"
        args.append(limit)
        return [_job_row(r) for r in await self._fetchall(sql, args)]

    async def delete_job(self, job_id: str) -> None:
        await self.conn.execute("DELETE FROM media_jobs WHERE id = ?", (job_id,))
        await self.conn.commit()

    # --- Divers --------------------------------------------------------

    async def kv_get(self, key: str) -> str | None:
        row = await self._fetchone("SELECT value FROM kv WHERE key = ?", (key,))
        return str(row["value"]) if row else None

    async def kv_set(self, key: str, value: str) -> None:
        await self.conn.execute(
            "INSERT INTO kv(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )
        await self.conn.commit()

    # --- Synchronisation (F7) ------------------------------------------

    async def export_since(self, since: float) -> dict[str, Any]:
        convs = await self._fetchall("SELECT * FROM conversations WHERE updated_at > ?", (since,))
        msgs = await self._fetchall("SELECT * FROM messages WHERE updated_at > ?", (since,))
        return {
            "conversations": [dict(r) for r in convs],
            "messages": [dict(r) for r in msgs],
            "until": now(),
        }

    async def import_sync(self, payload: dict[str, Any]) -> int:
        """Fusionne un lot distant (dernier écrit gagne). Renvoie le nombre de lignes appliquées."""
        applied = 0
        for c in payload.get("conversations", []):
            cur = await self.conn.execute(
                """INSERT INTO conversations(id, title, created_at, updated_at, summary,
                   summary_upto, deleted) VALUES (:id, :title, :created_at, :updated_at,
                   :summary, :summary_upto, :deleted)
                   ON CONFLICT(id) DO UPDATE SET title = excluded.title,
                   updated_at = excluded.updated_at, summary = excluded.summary,
                   summary_upto = excluded.summary_upto, deleted = excluded.deleted
                   WHERE excluded.updated_at > conversations.updated_at""",
                c,
            )
            applied += cur.rowcount
        for m in payload.get("messages", []):
            cur = await self.conn.execute(
                """INSERT INTO messages(uid, conversation_id, seq, role, body, model, created_at,
                   updated_at) VALUES (:uid, :conversation_id, :seq, :role, :body, :model,
                   :created_at, :updated_at)
                   ON CONFLICT(uid) DO UPDATE SET body = excluded.body,
                   updated_at = excluded.updated_at
                   WHERE excluded.updated_at > messages.updated_at""",
                m,
            )
            applied += cur.rowcount
        await self.conn.commit()
        return applied


def _job_row(row: aiosqlite.Row) -> dict[str, Any]:
    d = dict(row)
    d["params"] = json.loads(d.get("params") or "{}")
    return d
