"""Résultats intermédiaires des tâches complexes, gardés sur l'appareil (Android et Linux).

Dossier privé de l'application : `<données>/tasks/<discussion>/` (jamais vidé par le
système), avec un index. On y range :
- `part`  : le texte complet de chaque partie rédigée en parallèle ;
- `step`  : chaque étape livrée pas à pas ;
- `tool`  : les sorties d'outils longues (le fil n'en garde qu'un extrait et une référence) ;
- `draft` : les versions successives des fichiers créés (LaTeX, code…).
Le modèle peut les relire (`task_read`), l'utilisateur les voir, et ils sont synchronisés
(chiffrés) avec ses autres appareils. Effacés 7 jours après la fin de la tâche, ou avec la
discussion.
"""

from __future__ import annotations

import json
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

KEEP_DAYS = 7
MAX_ITEM = 1_000_000          # octets par élément (comme les créations synchronisées)
MAX_ITEMS = 200               # par discussion (les plus anciens sont retirés)
TOTAL_MAX = 300 * 1024 * 1024  # octets, toutes discussions (les plus anciens sont retirés)
TOOL_INLINE = 4000            # au-delà, une sortie d'outil est rangée ici
KINDS = ("part", "step", "tool", "draft")
_ID = re.compile(r"^[0-9a-f]{8,32}$")
_CID = re.compile(r"^[\w-]{1,64}$")


class TaskStore:
    def __init__(self, root: Path) -> None:
        self.root = root

    def _dir(self, cid: str) -> Path:
        if not _CID.match(cid):
            raise ValueError("discussion invalide")
        return self.root / cid

    def _index(self, cid: str) -> dict[str, Any]:
        try:
            data = json.loads((self._dir(cid) / "index.json").read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {"items": []}
        except (OSError, ValueError):
            return {"items": []}

    def _save_index(self, cid: str, index: dict[str, Any]) -> None:
        d = self._dir(cid)
        d.mkdir(parents=True, exist_ok=True)
        tmp = d / "index.json.tmp"
        tmp.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")
        tmp.replace(d / "index.json")

    def put(self, cid: str, kind: str, title: str, content: str, *,
            item_id: str | None = None, created: float | None = None,
            updated: float | None = None) -> dict[str, Any]:
        if kind not in KINDS:
            raise ValueError("type inconnu")
        data = content.encode("utf-8")[:MAX_ITEM]
        index = self._index(cid)
        iid = item_id if item_id and _ID.match(item_id) else uuid.uuid4().hex[:12]
        now = time.time()
        item = {"id": iid, "kind": kind, "title": title.strip()[:120] or kind,
                "size": len(data), "created": created or now, "updated": updated or now}
        items = [i for i in index["items"] if i["id"] != iid] + [item]
        for old in items[:-MAX_ITEMS]:
            (self._dir(cid) / f"{old['id']}.txt").unlink(missing_ok=True)
        index["items"] = items[-MAX_ITEMS:]
        index.pop("done_at", None)  # une tâche qui reprend n'est plus « terminée »
        self._dir(cid).mkdir(parents=True, exist_ok=True)
        (self._dir(cid) / f"{iid}.txt").write_bytes(data)
        self._save_index(cid, index)
        self._enforce_total()
        return item

    def _enforce_total(self) -> None:
        """Place totale bornée : les éléments les plus anciens partent d'abord."""
        if not self.root.is_dir():
            return
        entries = [(float(i.get("updated") or 0), d.name, i) for d in self.root.iterdir()
                   if d.is_dir() and _CID.match(d.name) for i in self._index(d.name)["items"]]
        total = sum(int(e[2].get("size") or 0) for e in entries)
        for _, cid, item in sorted(entries, key=lambda e: e[0]):
            if total <= TOTAL_MAX:
                break
            total -= int(item.get("size") or 0)
            (self._dir(cid) / f"{item['id']}.txt").unlink(missing_ok=True)
            index = self._index(cid)
            index["items"] = [i for i in index["items"] if i["id"] != item["id"]]
            self._save_index(cid, index)

    def items(self, cid: str) -> list[dict[str, Any]]:
        return list(self._index(cid)["items"])

    def read(self, cid: str, item_id: str, offset: int = 0, limit: int = 12000) -> str | None:
        if not _ID.match(item_id):
            return None
        try:
            text = (self._dir(cid) / f"{item_id}.txt").read_text(encoding="utf-8",
                                                                 errors="replace")
        except (OSError, ValueError):
            return None
        return text[max(0, offset):max(0, offset) + limit]

    def get(self, cid: str, item_id: str) -> dict[str, Any] | None:
        return next((i for i in self.items(cid) if i["id"] == item_id), None)

    def finish(self, cid: str) -> None:
        """Tâche terminée : le dossier sera effacé KEEP_DAYS jours plus tard."""
        index = self._index(cid)
        if index["items"]:
            index["done_at"] = time.time()
            self._save_index(cid, index)

    def delete(self, cid: str) -> None:
        shutil.rmtree(self._dir(cid), ignore_errors=True)

    def purge(self, now: float | None = None) -> int:
        """Efface les tâches terminées depuis plus de KEEP_DAYS jours."""
        now = now or time.time()
        removed = 0
        if not self.root.is_dir():
            return 0
        for d in self.root.iterdir():
            if not d.is_dir() or not _CID.match(d.name):
                continue
            done = self._index(d.name).get("done_at")
            if done and now - float(done) > KEEP_DAYS * 86400:
                shutil.rmtree(d, ignore_errors=True)
                removed += 1
        return removed

    def changed_since(self, since: float, limit: int = 30) -> list[tuple[str, dict[str, Any]]]:
        """Éléments modifiés depuis `since` (synchronisation), du plus ancien au plus récent."""
        out: list[tuple[str, dict[str, Any]]] = []
        if self.root.is_dir():
            for d in self.root.iterdir():
                if d.is_dir() and _CID.match(d.name):
                    out += [(d.name, i) for i in self._index(d.name)["items"]
                            if float(i.get("updated") or 0) > since]
        out.sort(key=lambda x: float(x[1].get("updated") or 0))
        return out[:limit]
