import { speak as speakApi } from "./api.js";
import { getLocale } from "./i18n.js";

const LANG_TAGS = { fr: "fr-FR", en: "en-US", mg: "mg-MG" };

export async function speakText(text, opts = {}) {
  const resp = await speakApi({ input: text, voice: opts.voice });
  const ct = resp.headers.get("content-type") || "";
  if (ct.includes("application/json")) {
    const body = await resp.json();
    if (body.local_tts) {
      speakWithBrowser(body.text || text);
      return;
    }
  }
  const blob = await resp.blob();
  const url = URL.createObjectURL(blob);
  const audio = new Audio(url);
  audio.addEventListener("ended", () => URL.revokeObjectURL(url));
  await audio.play();
}

export function speakWithBrowser(text) {
  if (!("speechSynthesis" in window)) return;
  const utter = new SpeechSynthesisUtterance(text);
  utter.lang = LANG_TAGS[getLocale()] || "fr-FR";
  window.speechSynthesis.cancel();
  window.speechSynthesis.speak(utter);
}
