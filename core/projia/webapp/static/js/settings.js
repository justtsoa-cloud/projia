import * as api from "./api.js";
import { t, setLocale, getLocale } from "./i18n.js";
import { toast } from "./toast.js";

export class SettingsView {
  constructor(root) {
    this.root = root;
    this.tab = "simple";
    this.render();
  }

  render() {
    this.root.innerHTML = "";
    const wrap = document.createElement("div");
    wrap.className = "settings-view";

    const tabs = document.createElement("div");
    tabs.className = "settings-tabs";
    const bSimple = document.createElement("button");
    bSimple.textContent = t("settings_simple");
    const bAdv = document.createElement("button");
    bAdv.textContent = t("settings_advanced");
    const setTab = (tab) => {
      this.tab = tab;
      bSimple.setAttribute("aria-selected", String(tab === "simple"));
      bAdv.setAttribute("aria-selected", String(tab === "advanced"));
      this.renderBody();
    };
    bSimple.onclick = () => setTab("simple");
    bAdv.onclick = () => setTab("advanced");
    tabs.append(bSimple, bAdv);
    wrap.appendChild(tabs);

    this.body = document.createElement("div");
    wrap.appendChild(this.body);
    this.root.appendChild(wrap);
    setTab(this.tab);
  }

  renderBody() {
    this.body.innerHTML = "";
    if (this.tab === "simple") this.renderSimple();
    else this.renderAdvanced();
  }

  group(title) {
    const g = document.createElement("div");
    g.className = "settings-group";
    const h = document.createElement("h3");
    h.textContent = title;
    g.appendChild(h);
    this.body.appendChild(g);
    return g;
  }

  fieldRow(group, label, hint, control) {
    const row = document.createElement("div");
    row.className = "field-row";
    const labelWrap = document.createElement("div");
    const l = document.createElement("label");
    l.textContent = label;
    labelWrap.appendChild(l);
    if (hint) {
      const h = document.createElement("span");
      h.className = "hint";
      h.textContent = hint;
      labelWrap.appendChild(h);
    }
    row.appendChild(labelWrap);
    row.appendChild(control);
    group.appendChild(row);
    return row;
  }

  async renderSimple() {
    const settings = await api.getSettings().catch(() => ({}));

    const gLang = this.group(t("settings_language"));
    const select = document.createElement("select");
    for (const [code, label] of [["fr", "Français"], ["en", "English"], ["mg", "Malagasy"]]) {
      const opt = document.createElement("option");
      opt.value = code;
      opt.textContent = label;
      if ((settings.language || getLocale()) === code) opt.selected = true;
      select.appendChild(opt);
    }
    select.onchange = async () => {
      setLocale(select.value);
      try {
        await api.putSettings({ language: select.value });
        toast(t("settings_save"));
      } catch (e) {
        toast(e.message, { error: true });
      }
    };
    this.fieldRow(gLang, t("settings_language"), null, select);

    const gKeys = this.group(t("settings_keys"));
    try {
      const providers = await api.getProviders();
      for (const p of providers) {
        const row = document.createElement("div");
        row.className = "provider-row";
        const name = document.createElement("span");
        name.className = "name";
        name.textContent = p.name || p.id;
        row.appendChild(name);
        const input = document.createElement("input");
        input.type = "password";
        input.placeholder = p.has_key ? "••••••••" : "sk-…";
        row.appendChild(input);
        const save = document.createElement("button");
        save.textContent = t("settings_save");
        save.onclick = async () => {
          if (!input.value) return;
          try {
            const res = await api.putKey(p.id, { key: input.value });
            toast(res.valid ? "✓" : res.detail || "…");
            input.value = "";
          } catch (e) {
            toast(e.message, { error: true });
          }
        };
        row.appendChild(save);
        if (p.has_key) {
          const del = document.createElement("button");
          del.className = "ghost";
          del.textContent = t("delete");
          del.onclick = async () => {
            await api.deleteKey(p.id);
            this.renderBody();
          };
          row.appendChild(del);
        }
        gKeys.appendChild(row);
      }
    } catch (e) {
      toast(e.message, { error: true });
    }

    const gAbout = this.group(t("settings_about"));
    try {
      const about = await api.getAbout();
      const p = document.createElement("div");
      p.style.fontSize = "13px";
      p.style.color = "var(--text-dim)";
      p.textContent = `Projia v${about.version || ""} — ${about.license || ""}`;
      gAbout.appendChild(p);
    } catch {
      /* about endpoint optional */
    }
    const clearBtn = document.createElement("button");
    clearBtn.textContent = "🧹 Vider le cache";
    clearBtn.onclick = async () => {
      await api.clearCache().catch((e) => toast(e.message, { error: true }));
      toast("✓");
    };
    gAbout.appendChild(clearBtn);
  }

  async renderAdvanced() {
    const gProviders = this.group(t("settings_custom_providers"));
    const list = document.createElement("div");
    gProviders.appendChild(list);
    const reloadProviders = async () => {
      list.innerHTML = "";
      try {
        const providers = await api.listCustomProviders();
        for (const p of providers) {
          const card = document.createElement("div");
          card.className = "custom-provider-card";
          card.textContent = `${p.name} — ${p.base_url}`;
          const del = document.createElement("button");
          del.className = "ghost";
          del.textContent = t("delete");
          del.onclick = async () => {
            await api.deleteCustomProvider(p.name);
            reloadProviders();
          };
          card.appendChild(del);
          list.appendChild(card);
        }
      } catch (e) {
        toast(e.message, { error: true });
      }
    };
    reloadProviders();

    const addRow = document.createElement("div");
    addRow.className = "field-row";
    const nameInput = document.createElement("input");
    nameInput.type = "text";
    nameInput.placeholder = "nom";
    const urlInput = document.createElement("input");
    urlInput.type = "text";
    urlInput.placeholder = "https://…/v1";
    const addBtn = document.createElement("button");
    addBtn.textContent = t("settings_add");
    addBtn.onclick = async () => {
      if (!nameInput.value || !urlInput.value) return;
      try {
        await api.addCustomProvider({ name: nameInput.value, base_url: urlInput.value, free: false, needs_key: true });
        nameInput.value = "";
        urlInput.value = "";
        reloadProviders();
      } catch (e) {
        toast(e.message, { error: true });
      }
    };
    addRow.append(nameInput, urlInput, addBtn);
    gProviders.appendChild(addRow);

    const gToken = this.group(t("settings_server_token"));
    const tokenInput = document.createElement("input");
    tokenInput.type = "password";
    tokenInput.value = api.getToken();
    tokenInput.placeholder = t("settings_server_token");
    const saveToken = document.createElement("button");
    saveToken.textContent = t("settings_save");
    saveToken.onclick = () => {
      api.setToken(tokenInput.value);
      toast("✓");
    };
    this.fieldRow(gToken, t("settings_server_token"), null, document.createElement("span"));
    gToken.appendChild(tokenInput);
    gToken.appendChild(saveToken);

    const gExport = this.group(t("settings_export"));
    const exportBtn = document.createElement("button");
    exportBtn.textContent = "⬇ " + t("settings_export");
    exportBtn.onclick = async () => {
      try {
        const data = await api.exportSettings();
        const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "projia-settings.json";
        a.click();
      } catch (e) {
        toast(e.message, { error: true });
      }
    };
    gExport.appendChild(exportBtn);

    const importInput = document.createElement("input");
    importInput.type = "file";
    importInput.accept = "application/json";
    importInput.onchange = async () => {
      const file = importInput.files[0];
      if (!file) return;
      try {
        const text = await file.text();
        await api.importSettings(JSON.parse(text));
        toast("✓");
      } catch (e) {
        toast(e.message, { error: true });
      }
    };
    gExport.appendChild(importInput);
  }
}
