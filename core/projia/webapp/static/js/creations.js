import * as api from "./api.js";
import { t } from "./i18n.js";
import { toast } from "./toast.js";

const FILTERS = [
  { key: "all", label: "gallery_all", kinds: null },
  { key: "images", label: "gallery_images", kinds: "image_gen,image_edit" },
  { key: "voices", label: "gallery_voices", kinds: "tts,music_sfx" },
  { key: "transcripts", label: "gallery_transcripts", kinds: "stt" },
  { key: "videos", label: "gallery_videos", kinds: "video_gen" },
];

export class CreationsView {
  constructor(root) {
    this.root = root;
    this.filter = "all";
    this.render();
  }

  render() {
    this.root.innerHTML = "";
    const wrap = document.createElement("div");
    wrap.className = "creations-view";

    const chips = document.createElement("div");
    chips.className = "filter-chips";
    for (const f of FILTERS) {
      const btn = document.createElement("button");
      btn.textContent = t(f.label);
      btn.setAttribute("aria-selected", String(f.key === this.filter));
      btn.onclick = () => {
        this.filter = f.key;
        chips.querySelectorAll("button").forEach((b) => b.setAttribute("aria-selected", "false"));
        btn.setAttribute("aria-selected", "true");
        this.loadGrid();
      };
      chips.appendChild(btn);
    }
    wrap.appendChild(chips);

    this.grid = document.createElement("div");
    this.grid.className = "gallery-grid";
    wrap.appendChild(this.grid);
    this.root.appendChild(wrap);
    this.loadGrid();
  }

  async loadGrid() {
    this.grid.innerHTML = "";
    const f = FILTERS.find((x) => x.key === this.filter);
    try {
      const params = { limit: 200 };
      if (f.kinds) params.kind = f.kinds;
      const jobs = await api.listMedia(params);
      if (!jobs || !jobs.length) {
        const empty = document.createElement("div");
        empty.className = "empty-gallery";
        empty.textContent = t("gallery_empty");
        this.grid.appendChild(empty);
        return;
      }
      for (const job of jobs) this.grid.appendChild(this.card(job));
    } catch (e) {
      toast(e.message, { error: true });
    }
  }

  card(job) {
    const el = document.createElement("div");
    el.className = "gallery-card" + (job.status !== "done" ? " " + (job.status === "failed" ? "failed" : "pending") : "");
    const thumb = document.createElement("div");
    thumb.className = "thumb";
    if (job.status === "done") {
      if (job.kind.startsWith("image")) {
        const img = document.createElement("img");
        img.src = api.mediaFileUrl(job.id);
        thumb.appendChild(img);
      } else if (job.kind === "video_gen") {
        const video = document.createElement("video");
        video.src = api.mediaFileUrl(job.id);
        video.muted = true;
        thumb.appendChild(video);
      } else {
        const span = document.createElement("span");
        span.className = "kind-icon";
        span.textContent = job.kind === "stt" ? "📝" : "🔊";
        thumb.appendChild(span);
      }
    } else {
      const span = document.createElement("span");
      span.className = "kind-icon";
      span.textContent = job.status === "failed" ? "⚠️" : "⏳";
      thumb.appendChild(span);
    }
    el.appendChild(thumb);

    const info = document.createElement("div");
    info.className = "info";
    const prompt = document.createElement("span");
    prompt.className = "prompt";
    prompt.textContent = job.prompt || job.params?.text || job.kind;
    info.appendChild(prompt);
    const row = document.createElement("div");
    row.className = "row";
    const date = document.createElement("span");
    date.textContent = job.created_at ? new Date(job.created_at).toLocaleDateString() : "";
    row.appendChild(date);
    const del = document.createElement("button");
    del.textContent = t("delete");
    del.onclick = async () => {
      await api.deleteMedia(job.id);
      this.loadGrid();
    };
    row.appendChild(del);
    info.appendChild(row);
    el.appendChild(info);
    return el;
  }
}
