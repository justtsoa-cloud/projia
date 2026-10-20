"""Discussion : tours de conversation (texte, fichiers, médias), reprise, historique, export."""

from __future__ import annotations

import asyncio
import base64
import contextlib
import time
import uuid
from collections.abc import AsyncIterator, Callable
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from projia import (
    importer,
    pdfexport,
)
from projia.agent import imagebrief, openlinks, planner
from projia.agent.loop import dumps
from projia.app_state import Core
from projia.catalog.models import Category
from projia.config import save_settings
from projia.creator import clarify
from projia.creator import intent as file_intent
from projia.explainer import intent as explainer_intent
from projia.explainer import service as explainer_service
from projia.router import imageintent
from projia.router.classifier import classify
from projia.router.refusal import looks_like_image_refusal
from projia.server import common
from projia.server.common import (
    MAX_TASK_VIEW,
    MEDIA_TURN_KINDS,
    REVIEWED_TOPICS,
    ChatBody,
    EditBody,
    FolderShareBody,
    Hub,
    ImportBody,
    LocalMediaBody,
    PinBody,
    RateLimiter,
    RenameBody,
    ResumeBody,
    _file_material,
    _first_image,
    _image_source,
    _keep_draft,
    _last_file,
    _media_history,
    _media_prompt,
    _references_image,
    _text_of,
    _wants_image,
    core_of,
)


def register(app: FastAPI, hub: Hub, ws_connects: RateLimiter) -> None:
    # --- API native : conversations ---------------------------------------


    async def _prefixed(first: list[dict[str, Any]],
                        gen: AsyncIterator[dict[str, Any]]) -> AsyncIterator[dict[str, Any]]:
        for ev in first:
            yield ev
        async for ev in gen:
            yield ev

    def _turn(core: Core, cid: str, gen: AsyncIterator[dict[str, Any]],
              first: list[dict[str, Any]] | None = None) -> StreamingResponse:
        """Lance un tour détaché (survit à la déconnexion du client) et diffuse son flux."""
        if core.turns.active(cid) is not None:
            raise HTTPException(409, "Une réponse est déjà en cours dans cette conversation")
        turn = core.turns.start(cid, _prefixed(first or [], gen))
        return _sse(turn.follow())

    def _sse(gen: AsyncIterator[dict[str, Any]]) -> StreamingResponse:
        async def run() -> AsyncIterator[str]:
            async for ev in gen:
                if ev["type"] in ("model_switched", "model_returned"):
                    hub.publish(ev)
                yield f"data: {dumps(ev)}\n\n"
            yield "data: {\"type\": \"end\"}\n\n"

        return StreamingResponse(run(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache",
                                          "X-Accel-Buffering": "no"})

    @app.post("/projia/chat")
    async def chat(request: Request, body: ChatBody) -> StreamingResponse:
        core = core_of(request)
        _first_image(body.content)  # valider avant de démarrer un tour détaché
        if body.conversation_id is None:
            core.catalog.refresh_in_background()  # veille « à chaque utilisation »
        file_kind = (body.category[5:] if body.category and body.category.startswith("file:")
                     else None)
        if file_kind is not None and not file_intent.valid(file_kind):
            raise HTTPException(400, "format de fichier inconnu")
        category = Category(body.category) if body.category and file_kind is None else None
        base_source: str | None = None
        if file_kind is None and body.category is None:
            # Avec ou sans photo : « traite l'exercice de la photo, rends la réponse en pdf ».
            file_kind = file_intent.detect(_text_of(body.content))
            if file_kind is None and body.conversation_id and not _first_image(body.content):
                # « Rajoute des détails », « traduis-la »… juste après un fichier créé :
                # on modifie CE fichier (même format, version précédente reprise).
                prev = await _last_file(core, body.conversation_id)
                if prev is not None and file_intent.is_revision(_text_of(body.content)):
                    file_kind, base_source = prev
        completed: str | None = None
        if (file_kind is None and body.category is None and body.conversation_id
                and not _first_image(body.content)):
            # Réponse aux questions posées avant une création : la création reprend, avec la
            # demande d'origine complétée par les choix (« Pour qui ? → Lycéens »).
            answer = _text_of(body.content)
            pend = clarify.pending_creation(await core.db.get_window(body.conversation_id, 6))
            if pend is not None and ("→" in answer or len(answer.split()) <= 12):
                file_kind, completed = pend[0], f"{pend[1]}\n{answer}"
        if file_kind is not None:
            category = None
        elif category is None:
            # Modalité détectée automatiquement (« dessine… », « crée la photo », « vas-y »
            # après une demande d'image…) : aucun mode à choisir pour l'utilisateur.
            prior: list[dict[str, Any]] = []
            if body.conversation_id and await core.db.conversation_exists(body.conversation_id):
                prior = await _media_history(core, body.conversation_id)
            detected = classify([*prior, {"role": "user", "content": body.content}]).category
            if detected.value in MEDIA_TURN_KINDS:
                category = detected
        # La conversation est créée d'abord : le tour lui est rattaché dès le départ.
        cid = body.conversation_id
        first: list[dict[str, Any]] = []
        if not cid or not await core.db.conversation_exists(cid):
            text = body.content if isinstance(body.content, str) else next(
                (p.get("text", "") for p in body.content if p.get("type") == "text"), "")
            cid = await core.db.create_conversation(text[:60].strip(), cid)
            first.append({"type": "conversation", "id": cid})
        body.conversation_id = cid
        if body.mode is not None:
            await core.db.set_mode(cid, f"learn:{body.level or 'lycee'}" if body.mode == "learn"
                                   else f"agent:{body.agent or 'auto'}" if body.mode == "agent"
                                   else "")
        if body.category is None and file_kind is None and not _first_image(body.content):
            # « Fais-moi une vidéo qui explique… » (mode Apprendre) : vidéo explicative, pas un
            # modèle de vidéo générative qui ne sait ni écrire une formule ni raisonner.
            stored_mode = await core.db.get_mode(cid)
            ex = explainer_intent.resolve(_text_of(body.content),
                                          learn_mode=stored_mode.startswith("learn"))
            if ex.active:
                return _turn(core, cid, _explainer_turn(core, body, cid, ex, stored_mode),
                             first)
        if file_kind is not None and completed is None and base_source is None and (
                body.mode != "learn" and not _first_image(body.content)):
            questions = clarify.questions_for(file_kind, _text_of(body.content),
                                              core.settings.language)
            if questions:
                return _turn(core, cid, _ask_turn(core, cid, body, file_kind, questions), first)
        if file_kind is not None:
            return _turn(core, cid, _file_turn(core, body, file_kind, base_source, completed),
                         first)
        if ((body.orchestrate or core.settings.orchestrate) and core.orchestrator is not None
                and category is None
                and not _first_image(body.content) and body.mode != "learn"):
            plan = await core.orchestrator.decomposer.decompose(_text_of(body.content))
            # NOTE: Choix autonome - complexité faible : aucune orchestration (zéro latence
            # ajoutée, le découpage par expressions régulières prend moins d'une milliseconde).
            if plan.complexity != "low":
                return _turn(core, cid, _orchestrated_turn(core, cid, body, plan), first)
        if category is not None and category.value in MEDIA_TURN_KINDS:
            return _turn(core, cid, _media_turn(core, body, category), first)
        return _turn(core, cid, _text_turn(core, body, cid, category), first)

    async def _text_turn(core: Core, body: ChatBody, cid: str,
                         category: Category | None) -> AsyncIterator[dict[str, Any]]:
        """Tour de texte avec **bascule automatique** : si le modèle répond qu'il ne sait pas
        générer d'image alors que l'utilisateur en demandait une, on passe à la génération."""
        text = _text_of(body.content)
        user_seq = 0
        switch = False
        topic = ""
        final: dict[str, Any] | None = None
        async for ev in core.chat.send(cid, body.content, model=body.model, forced=category,
                                       strict=body.strict, use_tools=body.use_tools):
            if ev["type"] == "route":
                topic = str((ev.get("profile") or {}).get("category") or "")
            if ev["type"] == "done":
                final = ev
            if ev["type"] == "user_saved":
                user_seq = int(ev.get("seq") or 0)
            if (ev["type"] == "done" and _wants_image(text)
                    and looks_like_image_refusal(str((ev.get("message") or {}).get("content")))):
                switch = True
                break                     # on ne montre pas le refus
            yield ev
        answer = str(((final or {}).get("message") or {}).get("content") or "")
        if (final is not None and not switch and not (final.get("message") or {}).get("tool_calls")
                and openlinks.wants_open(text)
                and not (await core.db.get_mode(cid)).startswith("agent")):
            urls = openlinks.links_in(answer)
            if urls:  # « Ouvre le site… » : bouton sous la réponse (navigateur de l'appareil)
                yield {"type": "open_links", "urls": urls}
        if (not switch and final is not None and core.settings.team_review
                and topic in REVIEWED_TOPICS and len(answer) > 80
                and "```quiz" not in answer and "```flashcards" not in answer
                and not (final.get("message") or {}).get("tool_calls")):
            # Équipe de modèles : un second modèle d'une autre famille vérifie la réponse.
            yield {"type": "step", "step": "answer_reviewing"}
            # Le relecteur voit ce que le rédacteur a vu : documents joints et fin du fil (sans
            # quoi il prend le contenu d'un fichier joint pour une invention).
            doc = await core.chat._documents_block(cid, text)
            recent = await core.db.get_window(cid, 8)
            thread = "\n".join(f"[{m['role']}] {_text_of(m.get('content') or '')[:1500]}"
                               for m in recent[:-2] if m.get("role") in ("user", "assistant"))
            context = (str(doc["content"]) if doc else "") + ("\n\n" + thread if thread else "")
            verdict = await core.creator.review_answer(text, answer, str(final.get("model")),
                                                       context=context)
            yield {"type": "review", **verdict} if verdict else {"type": "step",
                                                                 "step": "doc_done"}
        if switch and user_seq:
            await core.db.truncate_after(cid, user_seq)
            yield {"type": "media_switch"}
            kind = Category.IMAGE_EDIT if _first_image(body.content) else Category.IMAGE_GEN
            async for ev in _media_turn(core, body, kind, add_user=False):
                yield ev

    async def _orchestrated_turn(core: Core, cid: str, body: ChatBody, plan: Any
                                 ) -> AsyncIterator[dict[str, Any]]:
        """Demande composée : sous-tâches en parallèle (puis dépendantes), fusion, mesures."""
        recent = await core.db.get_window(cid, 6)
        context = "\n".join(f"[{m['role']}] {_text_of(m.get('content') or '')[:1000]}"
                            for m in recent if m.get("role") in ("user", "assistant"))
        user = await core.db.add_message(cid, {"role": "user", "content": body.content})
        yield {"type": "user_saved", "uid": user["uid"], "seq": user["seq"]}
        yield {"type": "orchestration", "complexity": plan.complexity,
               "subtasks": [{"index": s.index, "text": s.text[:200],
                             "category": s.category.value, "depends": s.depends}
                            for s in plan.subtasks]}
        if core.orchestrator is None:
            return
        # Avancement des parties relayé en direct (modèle et rôle de chacune).
        events: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        running = asyncio.create_task(core.orchestrator.run(plan, context, events.put_nowait))
        while not running.done() or not events.empty():
            getter = asyncio.ensure_future(events.get())
            await asyncio.wait({getter, running}, return_when=asyncio.FIRST_COMPLETED)
            if getter.done():
                ev = getter.result()
                if ev.get("model"):
                    m = core.router.catalog.catalog.get(ev["model"])
                    ev["name"] = m.name if m else ev["model"]
                yield ev
            else:
                getter.cancel()
        out = running.result()
        msg = {"role": "assistant", "content": out["text"]}
        saved = await core.db.add_message(cid, msg, model=out["model"] or None)
        model = core.router.catalog.catalog.get(out["model"]) if out["model"] else None
        yield {"type": "done", "message": msg, "model": out["model"],
               "name": model.name if model else out["model"], "metrics": out["metrics"],
               "uid": saved["uid"], "conversation_id": cid}

    async def _explainer_turn(core: Core, body: ChatBody, cid: str, ex: Any, mode: str
                              ) -> AsyncIterator[dict[str, Any]]:
        """Vidéo explicative : demande complétée → scénario validé → bloc lu par l'application."""
        text = _text_of(body.content)
        history = await core.db.get_messages(cid)
        user = await core.db.add_message(cid, {"role": "user", "content": body.content})
        yield {"type": "user_saved", "uid": user["uid"], "seq": user["seq"]}
        yield {"type": "step", "step": "explainer_plan"}
        story, brief, model, fallback = await explainer_service.produce(core, text, history, ex,
                                                                        mode)
        if story is None:
            content = explainer_service.failure_message(core.settings.language)
        else:
            content = explainer_service.message_for(story, brief, fallback=fallback)
        msg = {"role": "assistant", "content": content}
        saved = await core.db.add_message(cid, msg, model=model or None)
        yield {"type": "delta", "content": content}
        yield {"type": "done", "message": msg, "model": model or None, "name": model or None,
               "uid": saved["uid"], "conversation_id": cid}

    async def _ask_turn(core: Core, cid: str, body: ChatBody, kind: str,
                        questions: list[dict[str, Any]]) -> AsyncIterator[dict[str, Any]]:
        """Création longue mal précisée : questions à choix d'abord (aucun appel de modèle)."""
        await core.db.add_message(cid, {"role": "user", "content": body.content})
        for m in clarify.ask_messages(kind, _text_of(body.content), questions):
            await core.db.add_message(cid, m)
        yield {"type": "question", "conversation_id": cid, "questions": questions}

    async def _file_turn(core: Core, body: ChatBody, kind: str, base_source: str | None = None,
                         request: str | None = None) -> AsyncIterator[dict[str, Any]]:
        """Création d'un fichier (DOCX, PDF, carte mentale…) par l'équipe de modèles :
        rédaction, vérification, correction ; le résultat est une carte « fichier »."""
        cid = str(body.conversation_id)
        text = request or _text_of(body.content)
        history = await core.db.get_window(cid, 12)
        context = "\n\n".join(
            f"[{m['role']}] {_text_of(m['content'])[:3000]}" for m in history[-6:]
            if m["role"] in ("user", "assistant") and not str(m["content"]).startswith("[média:")
        )[-9000:]
        # Matière à transformer (« convertis ce HTML en PDF », « mets ce document en Word ») :
        # documents joints à la discussion et source du dernier fichier créé, en entier.
        material = await _file_material(core, cid, skip_last=base_source is not None,
                                        request=text)
        if material:
            context = f"{material}\n\n{context}"
        await core.db.add_message(cid, {"role": "user", "content": body.content})
        done: dict[str, Any] = {}
        images = [str((p.get("image_url") or {}).get("url"))
                  for p in (body.content if isinstance(body.content, list) else [])
                  if isinstance(p, dict) and p.get("type") == "image_url"][:3]
        async for ev in core.creator.create(kind, text, conversation_id=cid, context=context,
                                            base=base_source, images=images):
            if ev["type"] == "job":
                done = ev
            yield ev
        job = {k: v for k, v in done.items() if k != "type"}
        _keep_draft(core, cid, job)
        note = f"[média:{job['id']}]"
        msg = await core.db.add_message(cid, {"role": "assistant", "content": note},
                                        model=job.get("model"))
        yield {"type": "done", "message": {"role": "assistant", "content": note},
               "model": job.get("model"), "uid": msg["uid"], "conversation_id": cid,
               "name": (job.get("params") or {}).get("model_name"), "job": job}

    async def _media_turn(core: Core, body: ChatBody, category: Category,
                          add_user: bool = True) -> AsyncIterator[dict[str, Any]]:
        """Tour de conversation dont le résultat est un média (image, voix, vidéo)."""
        text = _text_of(body.content)
        cid = body.conversation_id
        if not cid or not await core.db.conversation_exists(cid):
            cid = await core.db.create_conversation(text[:60])
            yield {"type": "conversation", "id": cid}
        if add_user:
            await core.db.add_message(cid, {"role": "user", "content": body.content})
        image = _first_image(body.content)
        source_job_id = None
        needs_image = category == Category.IMAGE_EDIT or (
            category == Category.VIDEO_GEN and _references_image(text))
        if image is None and needs_image:
            image, source_job_id = await _image_source(core, cid)
            if image is None:
                yield {"type": "error", "code": "media_reference_missing",
                       "message": "Aucune image disponible dans cette discussion. "
                                  "Joignez une image ou régénérez la création échouée."}
                return
        prompt = await _media_prompt(core, cid, text)
        intent = imageintent.resolve(text)
        if category == Category.IMAGE_GEN and image is None and intent.from_context \
                and prompt == text:
            # « Fais-en une image », « génère une image par rapport à la discussion » : le
            # prompt vient de la discussion, pas de la phrase de la demande.
            yield {"type": "step", "step": "image_brief"}
            history = await core.db.get_messages(cid)
            if history and history[-1].get("role") == "user":
                history = history[:-1]  # la demande elle-même n'est pas le sujet
            async def brief_model(messages: list[dict[str, Any]],
                                  accept: Callable[[str], bool]) -> str | None:
                return await core.router.quick(messages, 900, accept)

            # Prompt anglais (modèle) ou repli sans modèle : jamais d'attente en plus.
            prompt, _source = await imagebrief.build(history, text, brief_model)
        elif category in (Category.IMAGE_GEN, Category.VIDEO_GEN, Category.IMAGE_EDIT):
            prompt = await common._english_prompt(core, prompt)
        job = await core.media.submit(category.value, prompt, conversation_id=cid,
                                      model=body.model, input_bytes=image,
                                      params={"source_job_id": source_job_id,
                                              "input_mode": "image" if image else "text"},
                                      input_name="image.png")
        yield {"type": "job", **job}
        done = await core.media.wait(job["id"]) or job
        yield {"type": "job", **done}
        note = f"[média:{done['id']}]"      # l'état (réussi ou échec) est lu dans le job
        msg = await core.db.add_message(cid, {"role": "assistant", "content": note},
                                        model=done.get("model"))
        yield {"type": "done", "message": {"role": "assistant", "content": note},
               "model": done.get("model"), "uid": msg["uid"], "conversation_id": cid,
               "name": (done.get("params") or {}).get("model_name"),
               "job": done}


    @app.post("/projia/chat/{cid}/resume")
    async def resume(request: Request, cid: str, body: ResumeBody) -> StreamingResponse:
        core = core_of(request)
        return _turn(core, cid, core.chat.resume(cid, approved=body.approved, model=body.model))

    @app.post("/projia/chat/{cid}/regenerate")
    async def regenerate(request: Request, cid: str, body: ResumeBody | None = None
                         ) -> StreamingResponse:
        core = core_of(request)
        if core.turns.active(cid) is not None:
            raise HTTPException(409, "Une réponse est déjà en cours dans cette conversation")
        history = await core.db.get_messages(cid)
        last_user = next((m for m in reversed(history) if m["role"] == "user"), None)
        if last_user is not None:
            earlier = await _media_history(core, cid, history[:history.index(last_user)])
            kind = classify([*earlier, {"role": "user", "content": last_user["content"]}]).category
            if kind.value in MEDIA_TURN_KINDS:
                # Une demande d'image/voix se relance comme un média, pas comme du texte.
                await core.db.truncate_after(cid, last_user["_meta"]["seq"])
                media_body = ChatBody(conversation_id=cid, content=last_user["content"],
                                      model=body.model if body else None)
                return _turn(core, cid, _media_turn(core, media_body, kind, add_user=False))
        avoid = frozenset({body.avoid_model}) if body and body.avoid_model else frozenset()
        return _turn(core, cid, core.chat.regenerate(cid, model=body.model if body else None,
                                                     avoid=avoid))

    @app.post("/projia/chat/{cid}/edit")
    async def edit_message(request: Request, cid: str, body: EditBody) -> StreamingResponse:
        core = core_of(request)
        if core.turns.active(cid) is not None:
            raise HTTPException(409, "Une réponse est déjà en cours dans cette conversation")
        history = await core.db.get_messages(cid)
        target = next((m for m in history if m["_meta"]["seq"] == body.seq), None)
        if target is not None and target["role"] == "user":
            earlier = await _media_history(core, cid,
                                          [m for m in history if m["_meta"]["seq"] < body.seq])
            kind = classify([*earlier, {"role": "user", "content": body.content}]).category
            if kind.value in MEDIA_TURN_KINDS:
                # Message modifié en demande d'image/vidéo/voix : média, pas texte.
                await core.db.edit_message(cid, body.seq, {"role": "user", "content": body.content})
                await core.db.truncate_after(cid, body.seq)
                media_body = ChatBody(conversation_id=cid, content=body.content, model=body.model)
                return _turn(core, cid, _media_turn(core, media_body, kind, add_user=False))
        return _turn(core, cid, core.chat.edit_and_resend(cid, body.seq, body.content,
                                                          model=body.model))

    @app.get("/projia/chat/{cid}/stream")
    async def follow_turn(request: Request, cid: str) -> StreamingResponse:
        """Se rattacher au tour en cours (ou tout juste terminé) d'une conversation."""
        turn = core_of(request).turns.get(cid)

        async def empty() -> AsyncIterator[dict[str, Any]]:
            return
            yield {}

        return _sse(turn.follow() if turn is not None else empty())

    @app.post("/projia/chat/{cid}/stop")
    async def stop_turn(request: Request, cid: str) -> dict[str, bool]:
        return {"stopped": await core_of(request).turns.stop(cid)}

    @app.post("/projia/chat/local-media")
    async def local_media(request: Request, body: LocalMediaBody) -> dict[str, Any]:
        """Enregistre dans la conversation une retouche **faite sur l'appareil** (la photo n'a
        été envoyée à aucun service) : message, fichier, entrée de la galerie."""
        core = core_of(request)
        if len(body.result_b64) > 34_000_000:
            raise HTTPException(413, "Image trop volumineuse (25 Mo maximum)")
        try:
            data = base64.b64decode(body.result_b64, validate=True)
        except ValueError as exc:
            raise HTTPException(400, "Image invalide") from exc
        if body.kind not in ("image_edit", "image_gen"):
            raise HTTPException(400, "type invalide")
        text = _text_of(body.content)
        cid = body.conversation_id
        if not cid or not await core.db.conversation_exists(cid):
            cid = await core.db.create_conversation(text[:60].strip(), cid)
        await core.db.add_message(cid, {"role": "user", "content": body.content})
        job_id = uuid.uuid4().hex
        from projia.media.providers import ext_for

        path = core.media.dir / body.kind / f"{job_id}.{ext_for(body.mime)}"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        job = {"id": job_id, "kind": body.kind, "status": "done", "model": "local:retouche",
               "prompt": text, "result_path": str(path), "conversation_id": cid,
               "created_at": time.time(),
               "params": {"mime": body.mime, "warning": body.note,
                          "model_name": body.model_name}}
        await core.db.upsert_job(job)
        msg = await core.db.add_message(cid, {"role": "assistant",
                                              "content": f"[média:{job_id}]"},
                                        model="local:retouche")
        await core.media.purge()
        return {"conversation_id": cid, "job": job, "uid": msg["uid"]}

    @app.post("/projia/chat/{cid}/approve-paid")
    async def approve_paid(request: Request, cid: str) -> dict[str, bool]:
        core_of(request).router.approve_paid(cid)
        return {"ok": True}

    @app.get("/projia/conversations")
    async def conversations(request: Request, q: str | None = None, limit: int = 50,
                            offset: int = 0, folder: str | None = None) -> list[dict[str, Any]]:
        core = core_of(request)
        rows = await core.db.list_conversations(min(limit, 500), offset, q, folder)
        for c in rows:  # pastilles : en cours sur cet appareil / attend une réponse
            c["running"] = core.turns.active(c["id"]) is not None
            c["waiting"] = core.turns.waiting.get(c["id"], "")
        return rows

    @app.get("/projia/conversations/{cid}")
    async def conversation(request: Request, cid: str, after: int = 0,
                           limit: int | None = None, tail: int | None = None,
                           before: int | None = None) -> dict[str, Any]:
        """`tail=N` : les N derniers messages ; `before=seq&tail=N` : les N précédents (début
        d'un long fil chargé à la demande). `total` : nombre de messages du fil."""
        db = core_of(request).db
        if not await db.conversation_exists(cid):
            raise HTTPException(404, "Conversation introuvable")
        summary, covered = await db.get_summary(cid)
        messages = (await db.get_window(cid, tail, before) if tail
                    else await db.get_messages(cid, after, limit))
        return {"id": cid, "messages": messages, "total": await db.count_messages(cid),
                "feedback": await db.feedback_of(cid),
                "mode": await db.get_mode(cid), "summary": summary, "summary_covered": covered,
                "plan": planner.public(await db.get_plan(cid)),
                "active": core_of(request).turns.active(cid) is not None}

    @app.delete("/projia/conversations/{cid}/plan")
    async def drop_plan(request: Request, cid: str) -> dict[str, bool]:
        """Abandonner le plan en cours (la discussion continue normalement)."""
        await core_of(request).db.set_plan(cid, None)
        return {"ok": True}

    @app.post("/projia/conversations/{cid}/compact")
    async def compact_conversation(request: Request, cid: str) -> dict[str, Any]:
        """Compactage manuel : fiche structurée du début du fil (messages conservés)."""
        core = core_of(request)
        if not await core.db.conversation_exists(cid):
            raise HTTPException(404, "Conversation introuvable")
        ok = await core.chat.compact(cid)
        summary, covered = await core.db.get_summary(cid)
        return {"ok": ok, "summary": summary, "summary_covered": covered}


    @app.patch("/projia/conversations/{cid}")
    async def rename(request: Request, cid: str, body: RenameBody) -> dict[str, bool]:
        db = core_of(request).db
        if body.title is not None:
            await db.rename_conversation(cid, body.title)
        if body.folder is not None:
            await db.set_folder(cid, body.folder)
        return {"ok": True}

    @app.post("/projia/import")
    async def import_conversation(request: Request, body: ImportBody) -> dict[str, Any]:
        """Importe une discussion (lien de partage Claude/ChatGPT/Gemini, JSON ou texte) pour
        la continuer ici. Erreur 422 `{code, message, …}` ; `import_browser` demande à
        l'application d'ouvrir le lien dans une vue web puis de renvoyer `data`."""
        db = core_of(request).db
        try:
            if body.data:
                found = importer.parse_any(body.data)
            elif body.url:
                found = [await importer.fetch(body.url)]
            else:
                raise importer.ConversationImportError("import_empty", "Rien à importer.")
        except importer.ConversationImportError as exc:
            raise HTTPException(422, {"code": exc.code, "message": str(exc), **exc.extra}
                                ) from exc
        out = []
        for conv in found:
            cid = await db.create_conversation(conv.title)
            for m in conv.messages:
                await db.add_message(cid, {"role": m["role"], "content": m["text"]},
                                     model=f"import:{conv.source}" if m["role"] == "assistant"
                                     else None)
            if body.folder:
                await db.set_folder(cid, body.folder)
            out.append({"id": cid, "title": conv.title, "count": len(conv.messages),
                        "source": conv.source})
        return {"conversations": out}

    @app.get("/projia/folders")
    async def folders(request: Request) -> list[dict[str, Any]]:
        core = core_of(request)
        shared = set(core.settings.shared_folders)
        return [{**f, "shared": f["folder"] in shared} for f in await core.db.list_folders()]

    @app.put("/projia/folders/share")
    async def share_folder(request: Request, body: FolderShareBody) -> dict[str, bool]:
        """Active ou coupe le partage de contexte entre les discussions d'un dossier."""
        core = core_of(request)
        shared = [f for f in core.settings.shared_folders if f != body.folder]
        if body.share:
            shared.append(body.folder)
        core.settings.shared_folders = shared
        save_settings(core.settings)
        return {"ok": True}

    @app.put("/projia/conversations/{cid}/pin")
    async def pin(request: Request, cid: str, body: PinBody) -> dict[str, bool]:
        await core_of(request).db.pin_conversation(cid, body.pinned)
        return {"ok": True}

    @app.get("/projia/conversations/{cid}/export")
    async def export(request: Request, cid: str, format: str = "md",
                     lang: str = "fr") -> Response:
        """Export Markdown (par défaut) ou PDF d'une conversation (partage, archivage) ;
        le PDF est produit sur l'appareil, sans service en ligne."""
        db = core_of(request).db
        if not await db.conversation_exists(cid):
            raise HTTPException(404, "Conversation introuvable")
        if format not in ("md", "pdf"):
            raise HTTPException(400, "Format inconnu")
        convs = {c["id"]: c for c in await db.list_conversations(limit=10_000)}
        title = convs.get(cid, {}).get("title") or "Conversation"
        you = {"en": "You", "mg": "Ianao"}.get(lang, "Vous")
        turns: list[tuple[str, str, str]] = []
        for m in await db.get_messages(cid):
            if m["role"] not in ("user", "assistant"):
                continue
            content = m.get("content")
            if isinstance(content, list):
                content = "\n".join(p.get("text", "[image]") for p in content)
            if not content:
                continue
            model = "" if m["role"] == "user" else str(m["_meta"].get("model") or "")
            turns.append((you if m["role"] == "user" else "Projia", model, str(content)))
        if format == "pdf":
            pdf = await asyncio.to_thread(pdfexport.build, title, turns)
            return Response(pdf, media_type="application/pdf")
        lines = [f"# {title}", ""]
        for who, model, content in turns:
            lines += [f"**{who}**" + (f" · _{model}_" if model else ""), "", content, ""]
        return Response("\n".join(lines), media_type="text/markdown; charset=utf-8")

    @app.delete("/projia/conversations/{cid}")
    async def delete_conv(request: Request, cid: str) -> dict[str, bool]:
        core = core_of(request)
        await core.db.delete_conversation(cid)
        with contextlib.suppress(OSError, ValueError):
            core.chat.tasks.delete(cid)  # résultats intermédiaires effacés avec la discussion
        return {"ok": True}

    @app.get("/projia/conversations/{cid}/tasks")
    async def task_items(request: Request, cid: str) -> list[dict[str, Any]]:
        """Résultats intermédiaires de la tâche (parties, étapes, sorties, brouillons)."""
        try:
            return core_of(request).chat.tasks.items(cid)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc

    @app.get("/projia/conversations/{cid}/tasks/{item_id}")
    async def task_item(request: Request, cid: str, item_id: str) -> dict[str, Any]:
        store = core_of(request).chat.tasks
        try:
            item = store.get(cid, item_id)
            text = store.read(cid, item_id, 0, MAX_TASK_VIEW)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if item is None or text is None:
            raise HTTPException(404, "Élément introuvable")
        return {**item, "content": text}

    @app.get("/projia/cloud/tasks")
    async def cloud_tasks(request: Request, since: float = 0) -> dict[str, Any]:
        """Résultats intermédiaires modifiés depuis `since`, avec leur contenu (chiffrés par
        l'application avant envoi)."""
        store = core_of(request).chat.tasks
        out, until = [], since
        for cid, item in store.changed_since(since):
            until = max(until, float(item.get("updated") or 0))
            out.append({**item, "conversation_id": cid,
                        "content": store.read(cid, item["id"], 0, 1_000_000) or ""})
        return {"items": out, "until": until}

    @app.post("/projia/cloud/tasks")
    async def cloud_tasks_import(request: Request) -> dict[str, int]:
        store = core_of(request).chat.tasks
        body = await request.json()
        applied = 0
        for it in (body.get("items") or [])[:50]:
            try:
                cid, iid = str(it["conversation_id"]), str(it["id"])
                mine = store.get(cid, iid)
                if mine is not None and float(mine.get("updated") or 0) >= float(it["updated"]):
                    continue
                store.put(cid, str(it["kind"]), str(it.get("title") or ""),
                          str(it.get("content") or ""), item_id=iid,
                          created=float(it.get("created") or 0) or None,
                          updated=float(it["updated"]))
                applied += 1
            except (KeyError, TypeError, ValueError, OSError):
                continue
        return {"applied": applied}
