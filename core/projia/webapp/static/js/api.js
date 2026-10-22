const TOKEN_KEY = "projia_token";

function consumeTokenFromUrl() {
  const params = new URLSearchParams(location.search);
  const token = params.get("token");
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
    params.delete("token");
    const q = params.toString();
    history.replaceState(null, "", location.pathname + (q ? "?" + q : "") + location.hash);
  }
}
consumeTokenFromUrl();

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* localStorage unavailable (private mode) — token simply won't persist */
  }
}

function authHeaders(extra) {
  const h = Object.assign({}, extra || {});
  const token = getToken();
  if (token) h["Authorization"] = "Bearer " + token;
  return h;
}

class ApiError extends Error {
  constructor(status, body) {
    super((body && body.error && body.error.message) || `Erreur ${status}`);
    this.status = status;
    this.body = body;
  }
}

export { ApiError };

async function handle(resp) {
  if (resp.status === 401) {
    const body = await resp.json().catch(() => ({}));
    throw new ApiError(401, body);
  }
  if (!resp.ok) {
    const body = await resp.json().catch(() => ({}));
    throw new ApiError(resp.status, body);
  }
  return resp;
}

export async function getJson(path) {
  const resp = await handle(await fetch(path, { headers: authHeaders() }));
  return resp.json();
}

export async function sendJson(path, method, body) {
  const resp = await handle(
    await fetch(path, {
      method,
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  );
  const ct = resp.headers.get("content-type") || "";
  if (ct.includes("application/json")) return resp.json();
  return resp;
}

export async function del(path) {
  return sendJson(path, "DELETE");
}

export async function upload(path, formData) {
  const resp = await handle(
    await fetch(path, { method: "POST", headers: authHeaders(), body: formData })
  );
  const ct = resp.headers.get("content-type") || "";
  if (ct.includes("application/json")) return resp.json();
  return resp;
}

export async function streamPost(path, body) {
  return handle(
    await fetch(path, {
      method: "POST",
      headers: authHeaders({ "Content-Type": "application/json" }),
      body: JSON.stringify(body),
    })
  );
}

// --- Endpoint helpers -------------------------------------------------

export const listConversations = (params = {}) => {
  const qs = new URLSearchParams(params).toString();
  return getJson("/projia/conversations" + (qs ? "?" + qs : ""));
};
export const getConversation = (cid, params = {}) => {
  const qs = new URLSearchParams(params).toString();
  return getJson(`/projia/conversations/${cid}` + (qs ? "?" + qs : ""));
};
export const renameConversation = (cid, body) => sendJson(`/projia/conversations/${cid}`, "PATCH", body);
export const pinConversation = (cid, pinned) => sendJson(`/projia/conversations/${cid}/pin`, "PUT", { pinned });
export const deleteConversation = (cid) => del(`/projia/conversations/${cid}`);
export const listFolders = () => getJson("/projia/folders");

export const chat = (body) => streamPost("/projia/chat", body);
export const chatResume = (cid, body) => streamPost(`/projia/chat/${cid}/resume`, body || {});
export const chatRegenerate = (cid, body) => streamPost(`/projia/chat/${cid}/regenerate`, body || {});
export const chatEdit = (cid, body) => streamPost(`/projia/chat/${cid}/edit`, body);
export const chatStop = (cid) => sendJson(`/projia/chat/${cid}/stop`, "POST");
export const chatReattach = (cid) => handle(fetch(`/projia/chat/${cid}/stream`, { headers: authHeaders() }));

export const submitMedia = (body) => sendJson("/projia/media", "POST", body);
export const listMedia = (params = {}) => {
  const qs = new URLSearchParams(params).toString();
  return getJson("/projia/media" + (qs ? "?" + qs : ""));
};
export const getMediaJob = (id) => getJson(`/projia/media/${id}`);
export const deleteMedia = (id) => del(`/projia/media/${id}`);
export const mediaFileUrl = (id) => `/projia/media/${id}/file`;

export const transcribe = (formData) => upload("/v1/audio/transcriptions", formData);
export const speak = (body) => {
  return fetch("/v1/audio/speech", {
    method: "POST",
    headers: authHeaders({ "Content-Type": "application/json" }),
    body: JSON.stringify(body),
  }).then(handle);
};

export const getHome = () => getJson("/projia/home");
export const dismissHome = (topic) => sendJson("/projia/home/dismiss", "POST", { topic });
export const getHealth = () => getJson("/projia/health");

export const getSettings = () => getJson("/projia/settings");
export const putSettings = (body) => sendJson("/projia/settings", "PUT", body);
export const getProviders = () => getJson("/projia/providers");
export const putKey = (provider, body) => sendJson(`/projia/keys/${provider}`, "PUT", body);
export const deleteKey = (provider) => del(`/projia/keys/${provider}`);
export const getAbout = () => getJson("/projia/about");
export const getStorage = () => getJson("/projia/storage");
export const clearCache = () => sendJson("/projia/storage/clear-cache", "POST");

export const listCustomProviders = () => getJson("/projia/custom-providers");
export const addCustomProvider = (body) => sendJson("/projia/custom-providers", "POST", body);
export const deleteCustomProvider = (name) => del(`/projia/custom-providers/${name}`);
export const exportSettings = () => getJson("/projia/settings/export");
export const importSettings = (body) => sendJson("/projia/settings/import", "POST", body);
