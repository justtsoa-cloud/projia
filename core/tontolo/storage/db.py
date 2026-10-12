"""Base SQLite (mode WAL) : historique canonique, quotas, dépenses, jobs médias.

Les messages sont stockés au format OpenAI canonique (indépendant du
fournisseur) ; chaque message garde le modèle qui l'a produit. Les médias
restent sur disque : la base ne contient que leur chemin.
"""

from __future__ import annotations

import json
import math
import re
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

CREATE TABLE IF NOT EXISTS memories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    text TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT 'fact',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    uses INTEGER NOT NULL DEFAULT 0,
    last_used REAL NOT NULL DEFAULT 0,
    source TEXT
);

CREATE TABLE IF NOT EXISTS kv (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    name TEXT NOT NULL,
    pages TEXT NOT NULL,
    chars INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_documents_conv ON documents(conversation_id);

CREATE TABLE IF NOT EXISTS answers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    conversation_id TEXT NOT NULL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    model TEXT NOT NULL DEFAULT '',
    vec TEXT NOT NULL,
    created_at REAL NOT NULL,
    uses INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_answers_conv ON answers(conversation_id);

CREATE TABLE IF NOT EXISTS feedback (
    uid TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL,
    model TEXT NOT NULL,
    category TEXT NOT NULL,
    rating INTEGER NOT NULL CHECK (rating IN (-1, 1)),
    reason TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL
);
"""


def _snippet(body: str | None, query: str, width: int = 90) -> str:
    """Extrait du message trouvé, centré sur le terme cherché."""
    if not body:
        return ""
    try:
        data = json.loads(body)
        content = data.get("content")
        text = content if isinstance(content, str) else " ".join(
            p.get("text", "") for p in content or [] if isinstance(p, dict))
    except (ValueError, AttributeError):
        text = body
    text = " ".join(str(text).split())
    i = text.lower().find(query.lower())
    if i < 0:
        return text[:width]
    start = max(0, i - width // 3)
    end = start + width
    return ("…" if start else "") + text[start:end] + ("…" if end < len(text) else "")


def now() -> float:
    return time.time()


def _safe_json(value: Any) -> str:
    """JSON sans demi-paire de substitution Unicode (un modèle peut en émettre : « \\ud800 »),
    qui ferait échouer l'écriture en base et perdre la réponse."""
    return json.dumps(value, ensure_ascii=False).encode("utf-8", "replace").decode("utf-8")


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
        await self._migrate()
        await self._conn.execute(
            "INSERT OR IGNORE INTO kv(key, value) VALUES ('schema_version', ?)",
            (str(SCHEMA_VERSION),),
        )
        await self._conn.commit()
        return self

    async def _migrate(self) -> None:
        """Migrations légères (ajout de colonnes) pour les bases existantes."""
        async with self.conn.execute("PRAGMA table_info(conversations)") as cur:
            cols = {r[1] for r in await cur.fetchall()}
        if "pinned" not in cols:
            await self.conn.execute(
                "ALTER TABLE conversations ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0")
        if "folder" not in cols:
            await self.conn.execute(
                "ALTER TABLE conversations ADD COLUMN folder TEXT NOT NULL DEFAULT ''")
        if "mode" not in cols:  # 0.3.0 : « » (général) ou « learn:<niveau> » (mode Apprendre)
            await self.conn.execute(
                "ALTER TABLE conversations ADD COLUMN mode TEXT NOT NULL DEFAULT ''")
        if "plan" not in cols:  # 0.5.1 : plan d'une tâche complexe (JSON), « » sinon
            await self.conn.execute(
                "ALTER TABLE conversations ADD COLUMN plan TEXT NOT NULL DEFAULT ''")
        async with self.conn.execute("PRAGMA table_info(documents)") as cur:
            doc_cols = {r[1] for r in await cur.fetchall()}
        if "digest" not in doc_cols:  # 0.6.0 : fiche compacte d'un long document
            await self.conn.execute(
                "ALTER TABLE documents ADD COLUMN digest TEXT NOT NULL DEFAULT ''")

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
        self, limit: int = 50, offset: int = 0, query: str | None = None,
        folder: str | None = None,
    ) -> list[dict[str, Any]]:
        """Conversations (épinglées d'abord). `query` : recherche plein texte (titre et
        messages, avec un extrait) ; `folder` : filtre par dossier (« » = sans dossier)."""
        where, args = "c.deleted = 0", []
        if folder is not None:
            where += " AND c.folder = ?"
            args.append(folder)
        if query:
            # `where` : fragments constants (paramètres liés) ; jamais de texte utilisateur.
            like = "%" + query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            rows = await self._fetchall(
                f"""SELECT c.id, c.title, c.created_at, c.updated_at, c.pinned, c.folder, c.mode,
                          (SELECT m.body FROM messages m WHERE m.conversation_id = c.id
                             AND m.body LIKE ? ESCAPE '\\' ORDER BY m.seq DESC LIMIT 1) AS hit
                   FROM conversations c
                   WHERE {where} AND (c.title LIKE ? ESCAPE '\\' OR EXISTS (
                         SELECT 1 FROM messages m WHERE m.conversation_id = c.id
                         AND m.body LIKE ? ESCAPE '\\'))
                   ORDER BY c.pinned DESC, c.updated_at DESC LIMIT ? OFFSET ?""",
                (like, *args, like, like, limit, offset),
            )
            out = []
            for r in rows:
                d = dict(r)
                d["snippet"] = _snippet(d.pop("hit"), query)
                out.append(d)
            return out
        rows = await self._fetchall(
            f"""SELECT c.id, c.title, c.created_at, c.updated_at, c.pinned, c.folder, c.mode
               FROM conversations c WHERE {where}
               ORDER BY c.pinned DESC, c.updated_at DESC LIMIT ? OFFSET ?""",
            (*args, limit, offset),
        )
        return [dict(r) for r in rows]

    async def get_title(self, cid: str) -> str:
        row = await self._fetchone("SELECT title FROM conversations WHERE id = ?", (cid,))
        return str(row["title"] or "") if row else ""

    async def get_folder(self, cid: str) -> str:
        row = await self._fetchone("SELECT folder FROM conversations WHERE id = ?", (cid,))
        return str(row["folder"] or "") if row else ""

    async def get_mode(self, cid: str) -> str:
        row = await self._fetchone("SELECT mode FROM conversations WHERE id = ?", (cid,))
        return str(row["mode"]) if row else ""

    async def set_mode(self, cid: str, mode: str) -> None:
        await self.conn.execute(
            "UPDATE conversations SET mode = ?, updated_at = ? WHERE id = ?",
            (mode[:40], now(), cid))
        await self.conn.commit()

    async def set_folder(self, cid: str, folder: str) -> None:
        await self.conn.execute(
            "UPDATE conversations SET folder = ?, updated_at = ? WHERE id = ?",
            (folder.strip()[:60], now(), cid))
        await self.conn.commit()

    async def list_folders(self) -> list[dict[str, Any]]:
        rows = await self._fetchall(
            "SELECT folder, COUNT(*) AS count FROM conversations WHERE deleted = 0 "
            "AND folder != '' GROUP BY folder ORDER BY folder COLLATE NOCASE")
        return [dict(r) for r in rows]

    async def rename_conversation(self, cid: str, title: str) -> None:
        await self.conn.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?", (title, now(), cid)
        )
        await self.conn.commit()

    async def pin_conversation(self, cid: str, pinned: bool) -> None:
        await self.conn.execute(
            "UPDATE conversations SET pinned = ?, updated_at = ? WHERE id = ?",
            (int(pinned), now(), cid))
        await self.conn.commit()

    async def truncate_after(self, cid: str, seq: int) -> None:
        """Supprime les messages après `seq` (régénérer / modifier et renvoyer)."""
        await self.conn.execute(
            "DELETE FROM messages WHERE conversation_id = ? AND seq > ?", (cid, seq))
        await self.conn.execute(
            "UPDATE conversations SET summary = NULL, summary_upto = 0, updated_at = ? "
            "WHERE id = ?", (now(), cid))
        await self.conn.commit()

    async def edit_message(self, cid: str, seq: int, message: dict[str, Any]) -> None:
        await self.conn.execute(
            "UPDATE messages SET body = ?, updated_at = ? WHERE conversation_id = ? AND seq = ?",
            (json.dumps(message, ensure_ascii=False), now(), cid, seq))
        await self.conn.execute("UPDATE conversations SET updated_at = ? WHERE id = ?",
                                (now(), cid))
        await self.conn.commit()

    async def delete_conversation(self, cid: str) -> None:
        # Suppression logique : propagée par la synchronisation. Les réponses mémorisées
        # (cache sémantique) de la discussion partent avec elle.
        await self.conn.execute("DELETE FROM answers WHERE conversation_id = ?", (cid,))
        await self.conn.execute(
            "UPDATE conversations SET deleted = 1, updated_at = ? WHERE id = ?", (now(), cid)
        )
        await self.conn.commit()

    # --- Réponses déjà données (cache sémantique, local, jamais synchronisé) ---------------

    async def add_answer(self, cid: str, question: str, answer: str, model: str, vec: str,
                         keep: int) -> None:
        await self.conn.execute(
            "INSERT INTO answers(conversation_id, question, answer, model, vec, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)", (cid, question, answer, model, vec, now()))
        # Taille bornée : les moins utilisées puis les plus anciennes partent.
        await self.conn.execute(
            "DELETE FROM answers WHERE id NOT IN (SELECT id FROM answers "
            "ORDER BY uses DESC, created_at DESC LIMIT ?)", (keep,))
        await self.conn.commit()

    async def list_answers(self) -> list[dict[str, Any]]:
        rows = await self._fetchall(
            "SELECT a.id, a.conversation_id, a.question, a.answer, a.model, a.vec, "
            "a.created_at, a.uses FROM answers a JOIN conversations c "
            "ON c.id = a.conversation_id WHERE c.deleted = 0")
        return [dict(r) for r in rows]

    async def touch_answer(self, answer_id: int) -> None:
        await self.conn.execute("UPDATE answers SET uses = uses + 1 WHERE id = ?", (answer_id,))
        await self.conn.commit()

    async def delete_answers(self, cid: str | None = None) -> int:
        """Réponses d'une discussion (régénérée, modifiée) ou toutes (`cid` None)."""
        cur = await (self.conn.execute("DELETE FROM answers WHERE conversation_id = ?", (cid,))
                     if cid else self.conn.execute("DELETE FROM answers"))
        await self.conn.commit()
        return cur.rowcount

    async def delete_answer_text(self, answer: str) -> None:
        """Une réponse jugée mauvaise n'est plus jamais réutilisée (cache sémantique)."""
        await self.conn.execute("DELETE FROM answers WHERE answer = ?", (answer,))
        await self.conn.commit()

    # --- Notes des réponses (👍 / 👎) -------------------------------------------------

    async def message_by_uid(self, uid: str) -> dict[str, Any] | None:
        row = await self._fetchone(
            "SELECT uid, conversation_id, seq, body, model FROM messages WHERE uid = ?", (uid,))
        if row is None:
            return None
        msg = json.loads(row["body"])
        msg["_meta"] = {"uid": row["uid"], "seq": row["seq"], "model": row["model"],
                        "conversation_id": row["conversation_id"]}
        return msg

    async def set_feedback(self, uid: str, cid: str, model: str, category: str, rating: int,
                           reason: str) -> None:
        await self.conn.execute(
            "INSERT INTO feedback(uid, conversation_id, model, category, rating, reason, "
            "created_at) VALUES (?, ?, ?, ?, ?, ?, ?) ON CONFLICT(uid) DO UPDATE SET "
            "rating = excluded.rating, reason = excluded.reason, created_at = excluded.created_at",
            (uid, cid, model, category, rating, reason, now()))
        await self.conn.commit()

    async def delete_feedback(self, uid: str) -> None:
        await self.conn.execute("DELETE FROM feedback WHERE uid = ?", (uid,))
        await self.conn.commit()

    async def feedback_of(self, cid: str) -> dict[str, int]:
        rows = await self._fetchall(
            "SELECT uid, rating FROM feedback WHERE conversation_id = ?", (cid,))
        return {str(r["uid"]): int(r["rating"]) for r in rows}

    async def feedback_totals(self) -> list[tuple[str, str, int, int]]:
        """(modèle, catégorie, 👍, 👎) sur les 180 derniers jours."""
        rows = await self._fetchall(
            "SELECT model, category, SUM(rating = 1) AS up, SUM(rating = -1) AS down "
            "FROM feedback WHERE created_at > ? GROUP BY model, category",
            (now() - 180 * 86400,))
        return [(str(r["model"]), str(r["category"]), int(r["up"] or 0), int(r["down"] or 0))
                for r in rows]

    async def count_answers(self) -> int:
        row = await self._fetchone("SELECT COUNT(*) AS n FROM answers")
        return int(row["n"]) if row else 0

    async def conversation_revision(self, cid: str) -> float | None:
        row = await self._fetchone(
            "SELECT updated_at FROM conversations WHERE id = ? AND deleted = 0", (cid,))
        return float(row["updated_at"]) if row else None

    async def set_summary(self, cid: str, summary: str, upto_seq: int,
                          expected_revision: float | None = None, *,
                          forward_only: bool = False) -> None:
        sql = "UPDATE conversations SET summary = ?, summary_upto = ? WHERE id = ? AND deleted = 0"
        args: list[Any] = [summary, upto_seq, cid]
        if expected_revision is not None:
            sql += " AND updated_at = ?"
            args.append(expected_revision)
        if forward_only:  # un résumé plus ancien n'écrase jamais un plus récent
            sql += " AND summary_upto < ?"
            args.append(upto_seq)
        await self.conn.execute(sql, args)
        await self.conn.commit()

    async def get_plan(self, cid: str) -> dict[str, Any] | None:
        row = await self._fetchone("SELECT plan FROM conversations WHERE id = ?", (cid,))
        try:
            plan = json.loads(row["plan"]) if row and row["plan"] else None
        except ValueError:
            return None
        return plan if isinstance(plan, dict) else None

    async def set_plan(self, cid: str, plan: dict[str, Any] | None) -> None:
        """Le plan est un état de travail : il ne change pas la date de la discussion."""
        await self.conn.execute(
            "UPDATE conversations SET plan = ? WHERE id = ?",
            (json.dumps(plan, ensure_ascii=False)[:60000] if plan else "", cid))
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
            (uid, cid, seq, message["role"], _safe_json(message), model, ts, ts),
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

    async def count_messages(self, cid: str) -> int:
        row = await self._fetchone("SELECT COUNT(*) AS n FROM messages WHERE conversation_id = ?",
                                   (cid,))
        return int(row["n"]) if row else 0

    async def get_window(self, cid: str, n: int, before_seq: int | None = None
                         ) -> list[dict[str, Any]]:
        """Les `n` derniers messages (ou les `n` qui précèdent `before_seq`), dans l'ordre.
        Un fil de plusieurs milliers de messages (photos comprises) ne se charge plus d'un bloc :
        l'application affiche la fin et va chercher le début à la demande."""
        sql = "SELECT uid, seq, body, model, created_at FROM messages WHERE conversation_id = ? "
        args: list[Any] = [cid]
        if before_seq is not None:
            sql += "AND seq < ? "
            args.append(before_seq)
        sql += "ORDER BY seq DESC LIMIT ?"
        args.append(max(1, min(n, 1000)))
        rows = list(reversed(await self._fetchall(sql, args)))
        out = []
        for r in rows:
            msg = json.loads(r["body"])
            msg["_meta"] = {"uid": r["uid"], "seq": r["seq"], "model": r["model"],
                            "created_at": r["created_at"]}
            out.append(msg)
        # le morceau commence sur une demande de l'utilisateur (jamais sur un résultat d'outil)
        first_user = next((i for i, m in enumerate(out) if m.get("role") == "user"), 0)
        return out[first_user:] if len(out) > 1 else out

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

    async def jobs_since(self, since: float, limit: int = 20) -> list[dict[str, Any]]:
        """Créations terminées modifiées depuis `since` (synchronisation par compte)."""
        rows = await self._fetchall(
            "SELECT * FROM media_jobs WHERE status = 'done' AND updated_at > ? "
            "AND result_path IS NOT NULL ORDER BY updated_at LIMIT ?", (since, limit))
        return [_job_row(r) for r in rows]

    async def delete_job(self, job_id: str) -> None:
        await self.conn.execute("DELETE FROM media_jobs WHERE id = ?", (job_id,))
        await self.conn.commit()

    # --- Mémoire à long terme -----------------------------------------

    # --- Documents joints ------------------------------------------------

    async def add_document(self, cid: str, doc_id: str, name: str, pages: list[str],
                           digest: str = "") -> None:
        await self.conn.execute(
            "INSERT INTO documents(id, conversation_id, name, pages, chars, created_at, digest) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (doc_id, cid, name, json.dumps(pages, ensure_ascii=False),
             sum(len(p) for p in pages), now(), digest))
        await self.conn.commit()

    async def list_documents(self, cid: str, with_pages: bool = False) -> list[dict[str, Any]]:
        rows = await self._fetchall(
            "SELECT * FROM documents WHERE conversation_id = ? ORDER BY created_at", (cid,))
        out = []
        for r in rows:
            d = dict(r)
            pages = d.pop("pages")
            if with_pages:
                d["pages"] = json.loads(pages)
            else:
                d.pop("digest", None)  # liste légère pour l'application
            out.append(d)
        return out

    async def delete_document(self, cid: str, doc_id: str) -> None:
        await self.conn.execute(
            "DELETE FROM documents WHERE id = ? AND conversation_id = ?", (doc_id, cid))
        await self.conn.commit()

    async def list_memories(self) -> list[dict[str, Any]]:
        rows = await self._fetchall("SELECT * FROM memories ORDER BY updated_at DESC")
        return [dict(r) for r in rows]

    async def add_memory(self, text: str, kind: str = "fact", source: str | None = None) -> int:
        ts = now()
        cur = await self.conn.execute(
            "INSERT INTO memories(text, kind, created_at, updated_at, source) "
            "VALUES (?, ?, ?, ?, ?)",
            (text, kind, ts, ts, source),
        )
        await self.conn.commit()
        return int(cur.lastrowid or 0)

    async def update_memory(self, mem_id: int, text: str) -> None:
        await self.conn.execute(
            "UPDATE memories SET text = ?, updated_at = ? WHERE id = ?", (text, now(), mem_id))
        await self.conn.commit()

    async def touch_memories(self, ids: list[int]) -> None:
        if not ids:
            return
        ts = now()
        await self.conn.executemany(
            "UPDATE memories SET uses = uses + 1, last_used = ? WHERE id = ?",
            [(ts, i) for i in ids])
        await self.conn.commit()

    async def delete_memory(self, mem_id: int | None = None) -> None:
        if mem_id is None:
            await self.conn.execute("DELETE FROM memories")
        else:
            await self.conn.execute("DELETE FROM memories WHERE id = ?", (mem_id,))
        await self.conn.commit()

    async def replace_memories(self, items: list[dict[str, Any]]) -> None:
        """Remplace toute la mémoire (résultat d'un compactage), en une transaction."""
        ts = now()
        await self.conn.execute("DELETE FROM memories")
        await self.conn.executemany(
            "INSERT INTO memories(id, text, kind, created_at, updated_at, uses, last_used, source) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            [(i.get("id"), i["text"], i.get("kind", "fact"), i.get("created_at", ts), ts,
              int(i.get("uses", 0)), float(i.get("last_used", 0)), i.get("source")) for i in items])
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
            # Lots d'anciennes versions : sans épingle, dossier ni mode.
            c = {"pinned": 0, "folder": "", "mode": "", "summary": None, "summary_upto": 0,
                 "deleted": 0, **c}
            cur = await self.conn.execute(
                """INSERT INTO conversations(id, title, created_at, updated_at, summary,
                   summary_upto, deleted, pinned, folder, mode) VALUES (:id, :title,
                   :created_at, :updated_at, :summary, :summary_upto, :deleted, :pinned,
                   :folder, :mode)
                   ON CONFLICT(id) DO UPDATE SET title = excluded.title,
                   updated_at = excluded.updated_at, summary = excluded.summary,
                   summary_upto = excluded.summary_upto, deleted = excluded.deleted,
                   pinned = excluded.pinned, folder = excluded.folder, mode = excluded.mode
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


    # --- Synchronisation par compte (0.3.0) : une conversation = un élément ---------------
    # Le dernier qui écrit gagne, conversation entière : suppressions, régénérations et
    # modifications se propagent sans doublons de messages.

    _CONV_SYNC_COLS = ("id", "title", "created_at", "updated_at", "deleted", "pinned", "folder",
                       "mode")

    async def export_conversations(self, since: float) -> list[dict[str, Any]]:
        cols = ", ".join(self._CONV_SYNC_COLS)
        convs = await self._fetchall(
            f"SELECT {cols} FROM conversations WHERE updated_at > ? ORDER BY updated_at",
            (since,))
        out = []
        for c in convs:
            d = dict(c)
            rows = [] if d["deleted"] else await self._fetchall(
                "SELECT uid, seq, role, body, model, created_at, updated_at FROM messages "
                "WHERE conversation_id = ? ORDER BY seq", (d["id"],))
            d["messages"] = [dict(r) for r in rows]
            out.append(d)
        return out

    async def replace_conversation(self, conv: dict[str, Any]) -> bool:
        """Applique une conversation venue d'un autre appareil si elle est plus récente.
        Tout est vérifié AVANT d'écrire (jamais de conversation à moitié remplacée)."""
        problem = sync_problem(conv)
        if problem:
            raise ValueError(problem)
        cid = str(conv["id"])
        row = await self._fetchone("SELECT updated_at FROM conversations WHERE id = ?", (cid,))
        if row is not None and float(row["updated_at"]) >= float(conv["updated_at"]):
            return False
        values = {k: conv.get(k) for k in self._CONV_SYNC_COLS}
        values.update(title=str(values["title"] or "")[:200], deleted=int(values["deleted"] or 0),
                      pinned=int(values["pinned"] or 0), folder=str(values["folder"] or "")[:60],
                      mode=str(values["mode"] or "")[:40])
        await self.conn.execute(
            """INSERT INTO conversations(id, title, created_at, updated_at, deleted, pinned,
               folder, mode) VALUES (:id, :title, :created_at, :updated_at, :deleted, :pinned,
               :folder, :mode)
               ON CONFLICT(id) DO UPDATE SET title = excluded.title,
               updated_at = excluded.updated_at, deleted = excluded.deleted,
               pinned = excluded.pinned, folder = excluded.folder, mode = excluded.mode,
               summary = NULL, summary_upto = 0""", values)
        await self.conn.execute("DELETE FROM messages WHERE conversation_id = ?", (cid,))
        for m in conv.get("messages") or []:
            await self.conn.execute(
                """INSERT OR REPLACE INTO messages(uid, conversation_id, seq, role, body, model,
                   created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (str(m["uid"]), cid, int(m["seq"]), str(m["role"]), str(m["body"]),
                 m.get("model"), float(m["created_at"]), float(m["updated_at"])))
        await self.conn.commit()
        return True


_SYNC_ROLES = frozenset({"user", "assistant", "tool", "system"})
_SYNC_ID = re.compile(r"^[\w-]{1,64}$")


def _finite(x: Any) -> bool:
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) and x >= 0


def sync_problem(conv: Any) -> str | None:
    """Raison du refus d'une conversation synchronisée, ou None si elle est bien formée."""
    if not isinstance(conv, dict):
        return "élément qui n'est pas une conversation"
    if not isinstance(conv.get("id"), str) or not _SYNC_ID.match(conv["id"]):
        return "identifiant invalide"
    if not _finite(conv.get("updated_at")) or not _finite(conv.get("created_at")):
        return "dates invalides"
    messages = conv.get("messages") or []
    if not isinstance(messages, list) or len(messages) > 50_000:
        return "liste de messages invalide"
    for m in messages:
        if not isinstance(m, dict):
            return "message illisible"
        if not isinstance(m.get("uid"), str) or not _SYNC_ID.match(m["uid"]):
            return "identifiant de message invalide"
        if not isinstance(m.get("seq"), int) or isinstance(m["seq"], bool) or m["seq"] < 0:
            return "position de message invalide"
        if m.get("role") not in _SYNC_ROLES:
            return "rôle de message invalide"
        body = m.get("body")
        if not isinstance(body, str) or len(body) > 5_000_000:
            return "contenu de message invalide"
        try:
            parsed = json.loads(body)
        except ValueError:
            return "contenu de message illisible"
        if not isinstance(parsed, dict) or parsed.get("role") != m["role"]:
            return "contenu de message incohérent"
        if not _finite(m.get("created_at")) or not _finite(m.get("updated_at")):
            return "dates de message invalides"
        if m.get("model") is not None and (not isinstance(m["model"], str)
                                           or len(m["model"]) > 200):
            return "modèle de message invalide"
    return None


def _job_row(row: aiosqlite.Row) -> dict[str, Any]:
    d = dict(row)
    d["params"] = json.loads(d.get("params") or "{}")
    return d
