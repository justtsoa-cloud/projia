// Visionneuse plein écran pour une image/vidéo générée, avec téléchargement.
let overlay = null;

function close() {
  if (overlay) {
    overlay.remove();
    overlay = null;
    document.removeEventListener("keydown", onKey);
  }
}

function onKey(e) {
  if (e.key === "Escape") close();
}

export function openLightbox(url, kind, filename) {
  close();
  overlay = document.createElement("div");
  overlay.className = "lightbox-overlay";
  overlay.onclick = (e) => {
    if (e.target === overlay) close();
  };

  const bar = document.createElement("div");
  bar.className = "lightbox-bar";
  const dl = document.createElement("a");
  dl.href = url;
  dl.download = filename || "projia";
  dl.className = "lightbox-btn";
  dl.textContent = "⬇ Télécharger";
  const closeBtn = document.createElement("button");
  closeBtn.className = "lightbox-btn";
  closeBtn.textContent = "✕";
  closeBtn.onclick = close;
  bar.append(dl, closeBtn);
  overlay.appendChild(bar);

  const media = kind === "video"
    ? Object.assign(document.createElement("video"), { src: url, controls: true, autoplay: true })
    : Object.assign(document.createElement("img"), { src: url, alt: "" });
  media.className = "lightbox-media";
  overlay.appendChild(media);

  document.body.appendChild(overlay);
  document.addEventListener("keydown", onKey);
}
