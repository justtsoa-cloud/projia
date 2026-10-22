import * as api from "./api.js";
import { setLocale, t } from "./i18n.js";
import { toast } from "./toast.js";
import { ChatView } from "./chat.js";
import { CreationsView } from "./creations.js";
import { SettingsView } from "./settings.js";

const viewEl = document.getElementById("view");
const navButtons = document.querySelectorAll("#main-nav button");
const healthDot = document.getElementById("health-dot");
const modelLabel = document.getElementById("model-chip-label");

let currentView = null;

function setActiveNav(route) {
  navButtons.forEach((b) => b.setAttribute("aria-selected", String(b.dataset.route === route)));
}

function route() {
  const hash = location.hash.replace(/^#/, "");
  const [name, arg] = hash.split("/");

  if (name === "creations") {
    setActiveNav("creations");
    viewEl.innerHTML = "";
    currentView = new CreationsView(viewEl);
    return;
  }
  if (name === "settings") {
    setActiveNav("settings");
    viewEl.innerHTML = "";
    currentView = new SettingsView(viewEl);
    return;
  }
  // default: chat
  setActiveNav("chat");
  if (!(currentView instanceof ChatView)) {
    viewEl.innerHTML = "";
    currentView = new ChatView(viewEl);
  }
  if (arg) currentView.openFromHash(arg);
  else if (!arg && name === "chat") currentView.open(null);
}

navButtons.forEach((btn) => {
  btn.addEventListener("click", () => {
    const r = btn.dataset.route;
    location.hash = r === "chat" ? "#chat" : "#" + r;
  });
});

window.addEventListener("hashchange", route);

async function pollHealth() {
  try {
    const h = await api.getHealth();
    healthDot.dataset.state = h.state === "green" || h.state === "orange" ? h.state : h.offline ? "red" : "";
    modelLabel.textContent = h.best || t("model_auto");
  } catch {
    healthDot.dataset.state = "";
  }
}

async function bootstrap() {
  try {
    const settings = await api.getSettings();
    if (settings.language) setLocale(settings.language);
  } catch {
    /* defaults to fr / no settings reachable yet (e.g. bad token) */
  }
  route();
  pollHealth();
  setInterval(pollHealth, 15000);
}

window.addEventListener("unhandledrejection", (e) => {
  if (e.reason && e.reason.status === 401) {
    toast(t("token_needed"), { error: true });
  }
});

bootstrap();
