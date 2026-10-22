// Parses a `text/event-stream` fetch() Response into an async generator of
// parsed JSON events. Stops on {"type": "end"} or when the stream closes.
export async function* parseSSE(response) {
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split("\n\n");
      buffer = parts.pop();
      for (const part of parts) {
        const line = part.split("\n").find((l) => l.startsWith("data:"));
        if (!line) continue;
        const raw = line.slice(5).trim();
        if (!raw) continue;
        let ev;
        try {
          ev = JSON.parse(raw);
        } catch {
          continue;
        }
        yield ev;
        if (ev.type === "end") return;
      }
    }
  } finally {
    reader.cancel().catch(() => {});
  }
}
