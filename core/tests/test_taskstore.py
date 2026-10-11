"""Résultats intermédiaires des tâches complexes : dossier privé, 7 jours, visibles et
synchronisés."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from tests.test_planner import COMPLEX, _chat, _script, client  # noqa: F401
from tontolo.agent.taskstore import KEEP_DAYS, TaskStore


def test_store_put_read_purge(tmp_path: Path) -> None:
    store = TaskStore(tmp_path)
    item = store.put("c1", "part", "Partie 1", "x" * 5000)
    assert store.read("c1", item["id"], 4990) == "x" * 10
    assert store.items("c1")[0]["title"] == "Partie 1"
    with pytest.raises(ValueError):
        store.put("../evil", "part", "t", "x")
    assert store.read("c1", "../index") is None
    store.finish("c1")
    assert store.purge() == 0
    assert store.purge(time.time() + KEEP_DAYS * 86400 + 10) == 1
    assert store.items("c1") == []


def test_parallel_parts_and_steps_are_kept(client: TestClient,  # noqa: F811
                                           fake: Any) -> None:
    seen: list[list[dict[str, Any]]] = []
    _script(fake, "parallel", seen)
    events = _chat(client, {"content": COMPLEX})
    cid = next(e["id"] for e in events if e["type"] == "conversation")
    items = client.get(f"/tontolo/conversations/{cid}/tasks").json()
    assert [i["kind"] for i in items] == ["part"] * 3
    one = client.get(f"/tontolo/conversations/{cid}/tasks/{items[0]['id']}").json()
    assert one["content"].startswith("partie par")
    plan = client.get(f"/tontolo/conversations/{cid}").json()["plan"]
    assert plan["status"] == "done" and all(r["ref"] for r in plan["results"])

    _script(fake, "steps", seen)
    events = _chat(client, {"content": COMPLEX})
    cid = next(e["id"] for e in events if e["type"] == "conversation")
    _chat(client, {"conversation_id": cid, "content": "continuer"})
    prompt = json.dumps(seen[-1], ensure_ascii=False)
    assert "Étape 1 livrée (texte complet : task_read id=" in prompt  # le fil ne se perd pas
    kinds = [i["kind"] for i in client.get(f"/tontolo/conversations/{cid}/tasks").json()]
    assert kinds == ["step", "step"]
    assert client.delete(f"/tontolo/conversations/{cid}").json()["ok"]
    assert client.get(f"/tontolo/conversations/{cid}/tasks").json() == []


def test_long_tool_output_is_stored(client: TestClient, fake: Any) -> None:  # noqa: F811
    core = client.app.state.core  # type: ignore[attr-defined]
    state = {"n": 0}

    async def big(args: dict[str, Any]) -> str:
        return "ligne\n" * 2000

    from tontolo.agent.tools import Tool

    core.chat.toolbox.add(Tool("gros_outil", "renvoie beaucoup", {"type": "object",
                                                                  "properties": {}}, big))

    def act(model: Any, messages: list[dict[str, Any]]) -> dict[str, Any]:
        state["n"] += 1
        if state["n"] == 1:
            return {"role": "assistant", "content": "", "tool_calls": [{
                "id": "g1", "type": "function",
                "function": {"name": "gros_outil", "arguments": "{}"}}]}
        return {"role": "assistant", "content": "fini"}

    for mid in ("coder-pro", "chatty", "small", "vision-x", "paid-genius"):
        fake.behaviors[mid] = act
    events = _chat(client, {"content": "lance l'outil"})
    cid = next(e["id"] for e in events if e["type"] == "conversation")
    msgs = client.get(f"/tontolo/conversations/{cid}").json()["messages"]
    tool_msg = next(m for m in msgs if m["role"] == "tool")
    assert len(tool_msg["content"]) < 3500 and "task_read id=" in tool_msg["content"]
    items = client.get(f"/tontolo/conversations/{cid}/tasks").json()
    assert items[0]["kind"] == "tool" and items[0]["size"] == 12000


def test_cloud_roundtrip(client: TestClient) -> None:  # noqa: F811
    core = client.app.state.core  # type: ignore[attr-defined]
    core.chat.tasks.put("c9", "draft", "livre.tex", "\\documentclass{book}")
    out = client.get("/tontolo/cloud/tasks").json()
    assert out["items"][0]["content"] == "\\documentclass{book}" and out["until"] > 0
    assert client.get("/tontolo/cloud/tasks", params={"since": out["until"]}).json()[
        "items"] == []
    item = dict(out["items"][0], conversation_id="c10", updated=out["until"] + 1)
    assert client.post("/tontolo/cloud/tasks", json={"items": [item]}).json() == {"applied": 1}
    assert client.post("/tontolo/cloud/tasks", json={"items": [item]}).json() == {"applied": 0}
    bad = dict(item, conversation_id="../x")
    assert client.post("/tontolo/cloud/tasks", json={"items": [bad]}).json() == {"applied": 0}
