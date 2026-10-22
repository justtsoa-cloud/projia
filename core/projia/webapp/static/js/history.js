import * as api from "./api.js";
import { t } from "./i18n.js";
import { toast } from "./toast.js";

export class ConversationList {
  constructor(container, { onSelect, activeId }) {
    this.container = container;
    this.onSelect = onSelect;
    this.activeId = activeId || null;
    this.query = "";
    this.items = [];
    this.render();
  }

  setActive(id) {
    this.activeId = id;
    this.renderList();
  }

  async reload() {
    try {
      this.items = await api.listConversations(this.query ? { q: this.query } : {});
    } catch (e) {
      toast(e.message, { error: true });
      this.items = [];
    }
    this.renderList();
  }

  render() {
    this.container.innerHTML = "";
    const head = document.createElement("div");
    head.className = "sidebar-head";
    const btnNew = document.createElement("button");
    btnNew.className = "primary";
    btnNew.textContent = "+ " + t("new_chat");
    btnNew.onclick = () => this.onSelect(null);
    const search = document.createElement("input");
    search.placeholder = t("search_placeholder");
    search.oninput = () => {
      this.query = search.value.trim();
      this.reload();
    };
    head.appendChild(btnNew);
    this.container.appendChild(head);
    this.container.appendChild(search);
    this.listEl = document.createElement("div");
    this.listEl.id = "conv-list";
    this.container.appendChild(this.listEl);
    this.reload();
  }

  renderList() {
    this.listEl.innerHTML = "";
    if (!this.items.length) {
      const empty = document.createElement("div");
      empty.style.padding = "16px";
      empty.style.color = "var(--text-dim)";
      empty.style.fontSize = "13px";
      empty.textContent = t("gallery_empty");
      this.listEl.appendChild(empty);
      return;
    }
    for (const conv of this.items) {
      const row = document.createElement("div");
      row.className = "conv-item" + (conv.id === this.activeId ? " active" : "");
      const title = document.createElement("span");
      title.className = "title";
      title.textContent = conv.title || "…";
      row.appendChild(title);
      if (conv.pinned) {
        const pin = document.createElement("span");
        pin.className = "pin";
        pin.textContent = "★";
        row.appendChild(pin);
      }
      const menu = document.createElement("button");
      menu.className = "ghost menu-btn";
      menu.textContent = "⋯";
      menu.onclick = (ev) => {
        ev.stopPropagation();
        this.showMenu(conv, menu);
      };
      row.appendChild(menu);
      row.onclick = () => this.onSelect(conv.id);
      this.listEl.appendChild(row);
    }
  }

  showMenu(conv, anchor) {
    const existing = document.querySelector(".conv-menu-popup");
    if (existing) existing.remove();
    const menu = document.createElement("div");
    menu.className = "conv-menu-popup";
    menu.style.position = "fixed";
    const rect = anchor.getBoundingClientRect();
    menu.style.top = rect.bottom + 4 + "px";
    menu.style.left = Math.max(8, rect.left - 120) + "px";
    menu.style.background = "var(--bg-elevated)";
    menu.style.border = "1px solid var(--border)";
    menu.style.borderRadius = "8px";
    menu.style.padding = "4px";
    menu.style.zIndex = "30";
    menu.style.display = "flex";
    menu.style.flexDirection = "column";
    menu.style.minWidth = "160px";

    const addItem = (label, fn) => {
      const b = document.createElement("button");
      b.className = "ghost";
      b.style.textAlign = "left";
      b.textContent = label;
      b.onclick = async (ev) => {
        ev.stopPropagation();
        menu.remove();
        await fn();
      };
      menu.appendChild(b);
    };

    addItem(t("conv_rename"), async () => {
      const title = prompt(t("conv_rename"), conv.title || "");
      if (title == null) return;
      await api.renameConversation(conv.id, { title });
      this.reload();
    });
    addItem(conv.pinned ? t("conv_unpin") : t("conv_pin"), async () => {
      await api.pinConversation(conv.id, !conv.pinned);
      this.reload();
    });
    addItem(t("conv_export_md"), () => {
      window.open(`/projia/conversations/${conv.id}/export?format=md`, "_blank");
    });
    addItem(t("conv_export_pdf"), () => {
      window.open(`/projia/conversations/${conv.id}/export?format=pdf`, "_blank");
    });
    addItem(t("conv_delete"), async () => {
      if (!confirm(t("conv_delete") + " ?")) return;
      await api.deleteConversation(conv.id);
      if (this.activeId === conv.id) this.onSelect(null);
      this.reload();
    });

    document.body.appendChild(menu);
    const closeOnce = (ev) => {
      if (!menu.contains(ev.target)) {
        menu.remove();
        document.removeEventListener("click", closeOnce);
      }
    };
    setTimeout(() => document.addEventListener("click", closeOnce), 0);
  }
}
