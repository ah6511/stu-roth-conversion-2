/**
 * Typed HTTP client for the Roth Conversion Planner FastAPI backend.
 */

function formatApiError(status, body) {
  if (body && typeof body === "object") {
    if (typeof body.detail === "string") {
      return body.detail;
    }
    if (Array.isArray(body.detail)) {
      return body.detail
        .map((err) => {
          const loc = Array.isArray(err.loc) ? err.loc.slice(1).join(".") : "";
          return loc ? `${loc}: ${err.msg}` : err.msg;
        })
        .join("; ");
    }
  }
  return `Request failed with status ${status}`;
}

async function requestJson(url, options = {}) {
  const res = await fetch(url, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    throw new Error(formatApiError(res.status, data));
  }
  return data;
}

export function fetchConfig(signal) {
  return requestJson("/api/config", { method: "GET", signal });
}

export function runSimulation(payload, signal) {
  return requestJson("/api/simulate", {
    method: "POST",
    body: JSON.stringify(payload),
    signal,
  });
}

export function runSweep(payload, signal) {
  return requestJson("/api/optimize/sweep", {
    method: "POST",
    body: JSON.stringify(payload),
    signal,
  });
}

export function runPerYearOptimize(payload, signal) {
  return requestJson("/api/optimize/per-year-dtb", {
    method: "POST",
    body: JSON.stringify(payload),
    signal,
  });
}

export function runDsbVsRate(payload, signal) {
  return requestJson("/api/optimize/dsb-vs-rate", {
    method: "POST",
    body: JSON.stringify(payload),
    signal,
  });
}

export function calcIncomeTax(payload, signal) {
  return requestJson("/api/calculators/income-tax", {
    method: "POST",
    body: JSON.stringify(payload),
    signal,
  });
}

export function calcCapitalGains(payload, signal) {
  return requestJson("/api/calculators/capital-gains", {
    method: "POST",
    body: JSON.stringify(payload),
    signal,
  });
}
