// Nom court et lisible d'une clé de modèle interne « fournisseur:modèle » (voir
// `ModelInfo.key` côté cœur : `f"{provider}:{model_id}"`). Même algorithme que
// `shortModelName()` dans app/lib/core/turn_progress.dart (Flutter), pour un rendu
// identique entre l'app et la webapp : « kilo:inclusionai/ling-3.1-flash » → « Ling 3.1 Flash ».
const DROP = new Set([
  "instruct", "chat", "it", "preview", "latest", "versatile", "free", "hf", "exp",
  "experimental", "turbo", "online", "fp8", "awq", "gguf",
]);

export function shortModelName(key) {
  if (!key) return "";
  let s = String(key).trim();
  // La clé interne est "fournisseur:modèle" — on affiche seulement la partie modèle.
  const firstColon = s.indexOf(":");
  if (firstColon >= 0) s = s.slice(firstColon + 1);
  if (s.includes("/")) s = s.split("/").pop();
  s = s.split(":")[0];
  s = s.replace(/\((free|gratuit)\)/gi, "");

  const words = [];
  for (const w of s.split(/[\s_-]+/)) {
    if (!w) continue;
    const low = w.toLowerCase();
    if (DROP.has(low)) continue;
    if (/^a\d+b$/.test(low) || /^\d{4,8}$/.test(low)) continue;
    if (/^\d+(\.\d+)?[bmk]$/.test(low)) {
      words.push(low.toUpperCase());
    } else if (w === low && /^[a-z]/.test(w)) {
      words.push(w[0].toUpperCase() + w.slice(1));
    } else {
      words.push(w);
    }
  }

  const kept = [];
  for (const w of words) {
    if (kept.length >= 3) break;
    if (/^\d+(\.\d+)?[BMK]$/.test(w) && kept.length === 0) continue;
    kept.push(w);
  }
  const out = kept.join(" ");
  return out.length > 24 ? out.slice(0, 23) + "…" : out;
}
