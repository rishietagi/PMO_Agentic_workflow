// API client for the FastAPI backend.

export async function getStatus() {
  const r = await fetch("/api/status");
  return r.json();
}

export async function getSampleSow() {
  const r = await fetch("/api/sample-sow");
  return (await r.json()).sow || "";
}

export async function getDashboard() {
  const r = await fetch("/api/dashboard");
  return r.json();
}

// Upload a SOW/RFP PDF; returns { sow, filename, pages, chars } or throws.
export async function uploadSowPdf(file) {
  const fd = new FormData();
  fd.append("file", file);
  const r = await fetch("/api/upload-sow", { method: "POST", body: fd });
  const data = await r.json();
  if (!r.ok) throw new Error(data.error || `upload failed (HTTP ${r.status})`);
  return data;
}

export async function submitFeedback(payload) {
  const r = await fetch("/api/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return r.json();
}

// Streams NDJSON events from /api/run; calls onEvent for each parsed line.
export async function runPipeline(body, onEvent) {
  const resp = await fetch("/api/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok || !resp.body) {
    throw new Error(`run failed: HTTP ${resp.status}`);
  }
  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let nl;
    while ((nl = buf.indexOf("\n")) >= 0) {
      const line = buf.slice(0, nl).trim();
      buf = buf.slice(nl + 1);
      if (line) onEvent(JSON.parse(line));
    }
  }
  if (buf.trim()) onEvent(JSON.parse(buf.trim()));
}
