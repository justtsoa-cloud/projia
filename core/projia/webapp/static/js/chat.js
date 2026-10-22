import * as api from "./api.js";
import { parseSSE } from "./sse.js";
import { t } from "./i18n.js";
import { toast } from "./toast.js";
import { ConversationList } from "./history.js";
import { Recorder } from "./media_record.js";
import { speakText } from "./speak.js";
import { shortModelName } from "./modelname.js";
import { openLightbox } from "./lightbox.js";

// Format exact du marqueur persisté pour un tour média (server/common.py,
// agent/loop.py:_MEDIA_NOTE) — même regex que chat_controller.dart côté Flutter.
const MEDIA_NOTE_RE = /^\[média:([0-9a-f]+)\]$/;

const MEDIA_KIND_TAG = {
  image_gen: "image", image_edit: "image",
  video_gen: "video",
  tts: "audio", music_sfx: "audio",
  stt: "text",
};

function textOf(content) {
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    return content
      .map((part) => (typeof part === "string" ? part : part && part.text))
      .filter(Boolean)
      .join("\n");
  }
  return "";
}

function imageUrlsOf(content) {
  if (!Array.isArray(content)) return [];
  return content
    .filter((part) => part && part.type === "image_url" && part.image_url)
    .map((part) => part.image_url.url)
    .filter(Boolean);
}

export class ChatView {
  constructor(root) {
    this.root = root;
    this.cid = null;
    this.recorder = new Recorder();
    this.jobPolls = new Map();
    this.mediaCardsByJobId = new Map();
    this.attachments = [];
    this.busy = false;
    this.lastFailureText = null;
    this.render();
  }

  render() {
    this.root.innerHTML = "";
    const wrap = document.createElement("div");
    wrap.className = "chat-view";

    const sidebar = document.createElement("div");
    sidebar.id = "sidebar";
    wrap.appendChild(sidebar);

    const main = document.createElement("div");
    main.id = "chat-main";

    this.messagesEl = document.createElement("div");
    this.messagesEl.id = "messages";
    main.appendChild(this.messagesEl);

    this.progressEl = document.createElement("div");
    this.progressEl.className = "progress-line";
    main.appendChild(this.progressEl);

    this.attachStrip = document.createElement("div");
    this.attachStrip.className = "attach-strip";
    this.attachStrip.hidden = true;
    main.appendChild(this.attachStrip);

    this.imageOptsPanel = this.buildImageOptsPanel();
    main.appendChild(this.imageOptsPanel);

    const composer = document.createElement("div");
    composer.id = "composer";

    this.fileInput = document.createElement("input");
    this.fileInput.type = "file";
    this.fileInput.accept = "image/*";
    this.fileInput.multiple = true;
    this.fileInput.hidden = true;
    this.fileInput.onchange = () => {
      this.addAttachments(Array.from(this.fileInput.files || []));
      this.fileInput.value = "";
    };
    composer.appendChild(this.fileInput);

    this.attachBtn = document.createElement("button");
    this.attachBtn.className = "icon-btn";
    this.attachBtn.textContent = "📎";
    this.attachBtn.title = "Joindre une image";
    this.attachBtn.onclick = () => this.fileInput.click();
    composer.appendChild(this.attachBtn);

    this.micBtn = document.createElement("button");
    this.micBtn.className = "icon-btn";
    this.micBtn.textContent = "🎙";
    this.micBtn.onclick = () => this.toggleRecording();
    composer.appendChild(this.micBtn);

    this.imageOptsBtn = document.createElement("button");
    this.imageOptsBtn.className = "icon-btn";
    this.imageOptsBtn.textContent = "🖼️";
    this.imageOptsBtn.title = "Choisir orientation et résolution d'image";
    this.imageOptsBtn.onclick = () => this.toggleImageOpts();
    composer.appendChild(this.imageOptsBtn);

    this.textarea = document.createElement("textarea");
    this.textarea.placeholder = t("composer_placeholder");
    this.textarea.rows = 1;
    this.textarea.addEventListener("input", () => this.resizeTextarea());
    this.textarea.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        this.send();
      }
    });
    composer.appendChild(this.textarea);

    this.sendBtn = document.createElement("button");
    this.sendBtn.className = "primary";
    this.sendBtn.textContent = t("send");
    this.sendBtn.onclick = () => this.send();
    composer.appendChild(this.sendBtn);

    main.appendChild(composer);
    wrap.appendChild(main);
    this.root.appendChild(wrap);

    this.convList = new ConversationList(sidebar, {
      onSelect: (cid) => this.open(cid),
      activeId: this.cid,
    });

    this.showEmpty();
    this.textarea.focus();
  }

  buildImageOptsPanel() {
    const panel = document.createElement("div");
    panel.className = "image-opts-panel";
    panel.hidden = true;

    const label1 = document.createElement("span");
    label1.textContent = "Format :";
    panel.appendChild(label1);
    this.orientationSelect = document.createElement("select");
    for (const [value, label] of [["16:9", "Paysage"], ["9:16", "Portrait"], ["1:1", "Carré"]]) {
      const opt = document.createElement("option");
      opt.value = value;
      opt.textContent = label;
      this.orientationSelect.appendChild(opt);
    }
    panel.appendChild(this.orientationSelect);

    const label2 = document.createElement("span");
    label2.textContent = "Résolution :";
    panel.appendChild(label2);
    this.resolutionSelect = document.createElement("select");
    for (const px of [720, 1080, 1440]) {
      const opt = document.createElement("option");
      opt.value = String(px);
      opt.textContent = px + " px";
      if (px === 1080) opt.selected = true;
      this.resolutionSelect.appendChild(opt);
    }
    panel.appendChild(this.resolutionSelect);

    const hint = document.createElement("span");
    hint.className = "hint";
    hint.textContent = "— décrivez l'image puis Envoyer";
    panel.appendChild(hint);

    return panel;
  }

  toggleImageOpts() {
    this.imageOptsPanel.hidden = !this.imageOptsPanel.hidden;
    this.imageOptsBtn.classList.toggle("active", !this.imageOptsPanel.hidden);
    if (!this.imageOptsPanel.hidden) this.textarea.focus();
  }

  async sendImageRequest() {
    if (this.busy) return;
    this.lastFailureText = null;
    const prompt = this.textarea.value.trim();
    const attachments = this.attachments;
    if (!prompt && !attachments.length) return;
    this.textarea.value = "";
    this.resizeTextarea();
    this.attachments = [];
    this.renderAttachStrip();
    if (this.messagesEl.querySelector(".empty-state")) this.messagesEl.innerHTML = "";

    const content = attachments.length
      ? [{ type: "text", text: prompt }, ...attachments.map((a) => ({ type: "image_url", image_url: { url: a.dataUrl } }))]
      : prompt;
    this.appendMessageBubble({ role: "user", content });

    const params = { aspect_ratio: this.orientationSelect.value, width: Number(this.resolutionSelect.value) };
    // Une pièce jointe → c'est une retouche/variation de CETTE image, pas une création
    // à partir de rien : on l'envoie comme image de référence et on bascule en image_edit.
    if (attachments.length) params.image = attachments[0].dataUrl;
    const kind = attachments.length ? "image_edit" : "image_gen";

    this.setBusy(true);
    try {
      const job = await api.submitMedia({ kind, prompt, conversation_id: this.cid, params });
      this.appendMediaCard(job);
    } catch (e) {
      toast(e.message, { error: true });
    } finally {
      this.setBusy(false);
    }
  }

  addAttachments(files) {
    for (const file of files) {
      if (!file.type.startsWith("image/")) continue;
      const reader = new FileReader();
      reader.onload = () => {
        this.attachments.push({ name: file.name, dataUrl: reader.result });
        this.renderAttachStrip();
      };
      reader.readAsDataURL(file);
    }
  }

  renderAttachStrip() {
    this.attachStrip.innerHTML = "";
    this.attachStrip.hidden = this.attachments.length === 0;
    this.attachments.forEach((a, i) => {
      const chip = document.createElement("div");
      chip.className = "attach-chip";
      const img = document.createElement("img");
      img.src = a.dataUrl;
      chip.appendChild(img);
      const remove = document.createElement("button");
      remove.className = "ghost";
      remove.textContent = "×";
      remove.onclick = () => {
        this.attachments.splice(i, 1);
        this.renderAttachStrip();
      };
      chip.appendChild(remove);
      this.attachStrip.appendChild(chip);
    });
  }

  showEmpty() {
    this.messagesEl.innerHTML = "";
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.innerHTML = `
      <img src="/assets/mark.svg" alt="">
      <h2>${t("empty_title")}</h2>
      <p>${t("empty_hint")}</p>
      <div class="chips">
        <button class="chip" data-s="${t("sugg_image")}">${t("sugg_image")}</button>
        <button class="chip" data-s="${t("sugg_video")}">${t("sugg_video")}</button>
        <button class="chip" data-s="${t("sugg_explain")}">${t("sugg_explain")}</button>
        <button class="chip" data-s="${t("sugg_translate")}">${t("sugg_translate")}</button>
      </div>`;
    empty.querySelectorAll(".chip").forEach((btn) => {
      btn.onclick = () => {
        this.textarea.value = btn.dataset.s;
        this.textarea.focus();
      };
    });
    this.messagesEl.appendChild(empty);
  }

  async open(cid) {
    this.cid = cid;
    this.convList.setActive(cid);
    if (!cid) {
      this.showEmpty();
      location.hash = "#chat";
      return;
    }
    location.hash = "#chat/" + cid;
    this.messagesEl.innerHTML = "";
    try {
      const data = await api.getConversation(cid, { limit: 500 });
      for (const msg of data.messages || []) this.appendMessageBubble(msg);
      this.scrollToBottom();
    } catch (e) {
      toast(e.message, { error: true });
    }
    this.textarea.focus();
  }

  appendMessageBubble(msg) {
    // Un tour média (image/audio/vidéo) est persisté comme un message assistant dont
    // le contenu est LITTÉRALEMENT "[média:<id du job>]" (voir server/common.py et
    // chat.py) : jamais du texte à afficher tel quel, toujours à résoudre en vrai média.
    const mediaMatch = MEDIA_NOTE_RE.exec(typeof msg.content === "string" ? msg.content.trim() : "");
    if (msg.role === "assistant" && mediaMatch) {
      return this.appendMediaNoteBubble(mediaMatch[1]);
    }
    const el = document.createElement("div");
    el.className = "msg " + (msg.role === "user" ? "user" : "assistant");
    for (const url of imageUrlsOf(msg.content)) {
      const img = document.createElement("img");
      img.className = "media media-clickable";
      img.src = url;
      img.title = "Cliquer pour agrandir";
      img.onclick = () => openLightbox(url, "image", "projia-piece-jointe.png");
      el.appendChild(img);
    }
    const body = document.createElement("span");
    body.className = "body";
    body.textContent = textOf(msg.content);
    el.appendChild(body);
    el.setText = (text) => {
      body.textContent = text;
    };
    if (msg.role === "assistant") {
      const meta = document.createElement("div");
      meta.className = "meta";
      if (msg._meta && msg._meta.model) {
        const span = document.createElement("span");
        span.textContent = shortModelName(msg._meta.model);
        meta.appendChild(span);
      }
      const listenBtn = document.createElement("button");
      listenBtn.className = "ghost";
      listenBtn.textContent = "🔊 " + t("listen");
      listenBtn.onclick = () => speakText(body.textContent).catch((e) => toast(e.message, { error: true }));
      meta.appendChild(listenBtn);
      el.appendChild(meta);
    }
    this.messagesEl.appendChild(el);
    this.scrollToBottom();
    return el;
  }

  appendBanner(cls, text, title) {
    const el = document.createElement("div");
    el.className = "banner " + cls;
    el.textContent = text;
    if (title && title !== text) el.title = title;
    this.messagesEl.appendChild(el);
    this.scrollToBottom();
    return el;
  }

  appendMediaNoteBubble(jobId) {
    const existing = this.mediaCardsByJobId.get(jobId);
    if (existing) return existing;
    const el = document.createElement("div");
    el.className = "msg assistant";
    el.dataset.jobId = jobId;
    const placeholder = document.createElement("div");
    placeholder.textContent = "⏳";
    el.appendChild(placeholder);
    this.messagesEl.appendChild(el);
    this.mediaCardsByJobId.set(jobId, el);
    this.scrollToBottom();
    api.getMediaJob(jobId)
      .then((job) => this.appendMediaCard(job))
      .catch(() => {
        placeholder.textContent = "⚠️ média introuvable";
      });
    return el;
  }

  appendMediaCard(job) {
    if (!job.id) return null;
    // Un même job traverse plusieurs événements (job "queued" puis job "done", et le
    // "done" du tour rappelle encore le même job) : mettre à jour LA carte existante,
    // jamais en créer une nouvelle pour le même id (sinon le média apparaît en double).
    const existing = this.mediaCardsByJobId.get(job.id);
    const el = existing || document.createElement("div");
    if (!existing) {
      el.className = "msg assistant";
      el.dataset.jobId = job.id;
      this.messagesEl.appendChild(el);
      this.mediaCardsByJobId.set(job.id, el);
    } else {
      el.innerHTML = "";
    }
    el.appendChild(this.renderMediaBody(job));
    this.scrollToBottom();
    if (job.status !== "done" && job.status !== "failed") this.pollJob(job.id, el);
    return el;
  }

  renderMediaBody(job) {
    const wrap = document.createElement("div");
    const kind = MEDIA_KIND_TAG[job.kind] || "file";
    if (job.status === "queued" || job.status === "running") {
      wrap.textContent = "⏳ " + (job.prompt || job.kind);
    } else if (job.status === "failed") {
      wrap.textContent = "⚠️ " + (job.error || job.kind);
    } else if (kind === "image") {
      const url = api.mediaFileUrl(job.id);
      const img = document.createElement("img");
      img.className = "media media-clickable";
      img.src = url;
      img.title = "Cliquer pour agrandir";
      img.onclick = () => openLightbox(url, "image", `projia-${job.id}.png`);
      wrap.appendChild(img);
    } else if (kind === "video") {
      const url = api.mediaFileUrl(job.id);
      const video = document.createElement("video");
      video.className = "media media-clickable";
      video.src = url;
      video.controls = true;
      video.title = "Cliquer pour agrandir";
      video.addEventListener("click", (e) => {
        // Ne pas ouvrir le lightbox quand on clique sur les contrôles natifs du lecteur.
        if (e.offsetY < video.clientHeight - 32) openLightbox(url, "video", `projia-${job.id}.mp4`);
      });
      wrap.appendChild(video);
    } else if (kind === "audio") {
      const audio = document.createElement("audio");
      audio.className = "media";
      audio.src = api.mediaFileUrl(job.id);
      audio.controls = true;
      wrap.appendChild(audio);
    } else {
      wrap.textContent = job.params?.text || job.prompt || job.kind;
    }
    return wrap;
  }

  pollJob(id, el) {
    if (this.jobPolls.has(id)) return;
    let delay = 800;
    const tick = async () => {
      try {
        const job = await api.getMediaJob(id);
        if (job.status === "done" || job.status === "failed") {
          el.innerHTML = "";
          el.appendChild(this.renderMediaBody(job));
          this.jobPolls.delete(id);
          this.scrollToBottom();
          return;
        }
      } catch {
        this.jobPolls.delete(id);
        return;
      }
      delay = Math.min(1500, delay + 200);
      this.jobPolls.set(id, setTimeout(tick, delay));
    };
    this.jobPolls.set(id, setTimeout(tick, delay));
  }

  setBusy(busy) {
    this.busy = busy;
    this.sendBtn.textContent = busy ? t("stop") : t("send");
    this.sendBtn.onclick = busy ? () => api.chatStop(this.cid).catch(() => {}) : () => this.send();
    this.textarea.disabled = busy && !this.cid;
  }

  async send() {
    // Garde-fou : une 2e requête pendant qu'un tour tourne déjà donne un 409
    // côté serveur ("Une réponse est déjà en cours dans cette conversation") —
    // on l'évite ici plutôt que de laisser l'utilisateur voir l'erreur.
    if (this.busy) return;
    if (this.imageOptsPanel && !this.imageOptsPanel.hidden) return this.sendImageRequest();
    this.lastFailureText = null;
    const text = this.textarea.value.trim();
    const attachments = this.attachments;
    if (!text && !attachments.length) return;
    this.textarea.value = "";
    this.resizeTextarea();
    this.attachments = [];
    this.renderAttachStrip();
    if (this.messagesEl.querySelector(".empty-state")) this.messagesEl.innerHTML = "";

    const content = attachments.length
      ? [{ type: "text", text }, ...attachments.map((a) => ({ type: "image_url", image_url: { url: a.dataUrl } }))]
      : text;
    this.appendMessageBubble({ role: "user", content });
    this.setBusy(true);

    let assistantEl = null;
    let assistantText = "";
    try {
      const resp = await api.chat({ conversation_id: this.cid, content });
      for await (const ev of parseSSE(resp)) {
        switch (ev.type) {
          case "conversation":
            this.cid = ev.id;
            this.convList.setActive(ev.id);
            this.convList.reload();
            location.hash = "#chat/" + ev.id;
            break;
          case "delta":
            if (!assistantEl) assistantEl = this.appendMessageBubble({ role: "assistant", content: "" });
            assistantText += ev.content || "";
            assistantEl.setText(assistantText);
            this.scrollToBottom();
            break;
          case "route": {
            const label = ev.name ? shortModelName(ev.name) : shortModelName(ev.model);
            this.progressEl.textContent = label ? `${label} · ${ev.reason || ""}` : "";
            break;
          }
          case "model_switched": {
            const from = shortModelName(ev.from);
            const to = shortModelName(ev.to);
            const short = `🔁 ${from} → ${to}`;
            const full = ev.reason ? `${t("banner_switched")}: ${from} → ${to} (${ev.reason})` : short;
            this.appendBanner("switch", short, full);
            break;
          }
          case "model_returned":
            this.appendBanner("ok", `↩️ ${shortModelName(ev.name || ev.model)}`, t("banner_returned"));
            break;
          case "waiting":
          case "step":
          case "orchestration":
          case "plan":
            this.progressEl.textContent = ev.step || ev.status || "…";
            break;
          case "review":
            this.appendBanner("ok", `✓ ${t("banner_reviewed")}`);
            break;
          case "job": {
            // Un job en échec répète parfois le même message agrégé sur deux
            // événements consécutifs (ex. toutes les sources d'image épuisées) :
            // éviter d'afficher deux cartes quasi identiques l'une sous l'autre.
            if (ev.status === "failed") {
              const raw = ev.error || ev.kind || "";
              if (raw && raw === this.lastFailureText) break;
              this.lastFailureText = raw;
            }
            this.appendMediaCard(ev);
            break;
          }
          case "media_switch":
            // {"type":"media_switch"} ne porte aucune donnée de job : un simple
            // indicateur de progression, pas une carte média à part entière.
            this.progressEl.textContent = "🔄 Nouvelle source média…";
            break;
          case "offline":
            this.appendBanner("error", `📡 ${t("banner_offline")}`);
            break;
          case "error": {
            const raw = ev.message || "";
            if (raw && raw === this.lastFailureText) break;
            this.lastFailureText = raw;
            this.appendBanner("error", `⚠️ ${t("banner_error")}: ${raw}`);
            break;
          }
            break;
          case "question":
            this.renderQuestion(ev);
            break;
          case "done":
            this.progressEl.textContent = "";
            if (ev.job) {
              // Tour média/fichier : le "done" rappelle le même job déjà vu via "job" —
              // mettre à jour la carte existante plutôt que recréer un message séparé.
              this.appendMediaCard(ev.job);
            } else if (assistantEl && ev.message) {
              assistantText = textOf(ev.message.content);
              assistantEl.setText(assistantText);
            } else if (ev.message && textOf(ev.message.content)) {
              this.appendMessageBubble(ev.message);
            }
            break;
          default:
            break;
        }
      }
    } catch (e) {
      toast(e.message, { error: true });
    } finally {
      this.setBusy(false);
      this.progressEl.textContent = "";
    }
  }

  renderQuestion(ev) {
    const wrap = document.createElement("div");
    wrap.className = "banner";
    const label = document.createElement("span");
    label.textContent = (ev.questions && ev.questions[0] && ev.questions[0].text) || "?";
    wrap.appendChild(label);
    this.messagesEl.appendChild(wrap);
    this.scrollToBottom();
  }

  async toggleRecording() {
    if (this.recorder.active) {
      this.micBtn.classList.remove("recording");
      const blob = await this.recorder.stop();
      if (!blob) return;
      const form = new FormData();
      form.append("file", blob, "dictation.webm");
      form.append("model", "auto");
      try {
        const res = await api.transcribe(form);
        // Remplace plutôt que d'accumuler : chaque dictée reflète exactement ce qui vient
        // d'être dit, pour éviter d'envoyer un texte reste d'une tentative précédente.
        this.textarea.value = res.text || "";
        this.resizeTextarea();
        this.textarea.focus();
      } catch (e) {
        toast(e.message, { error: true });
      }
    } else {
      try {
        await this.recorder.start();
        this.micBtn.classList.add("recording");
      } catch (e) {
        toast(e.message, { error: true });
      }
    }
  }

  scrollToBottom() {
    this.messagesEl.scrollTop = this.messagesEl.scrollHeight;
  }

  resizeTextarea() {
    this.textarea.style.height = "auto";
    this.textarea.style.height = Math.min(160, this.textarea.scrollHeight) + "px";
  }

  openFromHash(cid) {
    if (cid) this.open(cid);
  }
}
