async function expectOk(res) {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res;
}

export async function listWorkspaceRuns({ refresh = false } = {}) {
  const res = await expectOk(
    await fetch(`/api/runs${refresh ? "?refresh=1" : ""}`)
  );
  const data = await res.json();
  return Array.isArray(data.runs) ? data.runs : [];
}

export async function fetchRunSourceText(id) {
  const res = await expectOk(await fetch(`/api/run/${encodeURIComponent(id)}/source`));
  return res.text();
}

export async function fetchNormalizedRun(id) {
  const res = await expectOk(await fetch(`/api/run/${encodeURIComponent(id)}`));
  return res.json();
}

/** Fetches position limits from the server (authoritative source, same as backend/limits.py). */
export async function fetchLimits() {
  const res = await expectOk(await fetch("/api/limits"));
  const data = await res.json();
  return typeof data.limits === "object" && data.limits !== null ? data.limits : {};
}
