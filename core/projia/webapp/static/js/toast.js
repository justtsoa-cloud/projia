export function toast(message, { error = false, timeout = 5000 } = {}) {
  const stack = document.getElementById("toasts");
  if (!stack) return;
  const el = document.createElement("div");
  el.className = "toast" + (error ? " error" : "");
  el.textContent = message;
  stack.appendChild(el);
  setTimeout(() => el.remove(), timeout);
}
