// Cloudflare Worker: lets the public dashboard's "обновить" button kick off a
// real check_prices.py run on GitHub Actions, instead of just re-reading the
// cached data.json. The GitHub token lives only in this Worker's secret
// storage (env.GH_TOKEN) — it is never sent to or visible from the browser.
//
// Deploy: paste this file into a new Cloudflare Worker (Workers & Pages ->
// Create -> Create Worker -> Quick Edit), then add a secret named GH_TOKEN
// (Settings -> Variables and Secrets) holding a GitHub fine-grained PAT
// scoped to ONLY this repo with the single permission "Actions: Read and
// write". Update DASHBOARD_ORIGIN below if the Pages URL ever changes.

const OWNER = "ichikazau";
const REPO = "butterfly-watch";
const WORKFLOW = "check.yml";
const DASHBOARD_ORIGIN = "https://ichikazau.github.io";
const COOLDOWN_SECONDS = 60; // refuse to re-trigger while the last run is younger than this (or still running)

export default {
  async fetch(request, env) {
    const cors = {
      "Access-Control-Allow-Origin": DASHBOARD_ORIGIN,
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
    };

    if (request.method === "OPTIONS") {
      return new Response(null, { headers: cors });
    }
    if (request.method !== "POST") {
      return json({ ok: false, reason: "method_not_allowed" }, 405, cors);
    }

    const ghHeaders = {
      Authorization: `Bearer ${env.GH_TOKEN}`,
      Accept: "application/vnd.github+json",
      "User-Agent": "butterfly-watch-worker",
    };

    // Guard against spam: only allow a new run if the last one is finished
    // and older than COOLDOWN_SECONDS. GitHub itself is the source of truth
    // here, so this holds even if multiple Worker instances handle requests.
    const runsRes = await fetch(
      `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${WORKFLOW}/runs?per_page=1`,
      { headers: ghHeaders }
    );
    if (!runsRes.ok) {
      return json({ ok: false, reason: "github_unreachable" }, 502, cors);
    }
    const runsData = await runsRes.json();
    const lastRun = runsData.workflow_runs && runsData.workflow_runs[0];
    if (lastRun) {
      const ageSec = (Date.now() - new Date(lastRun.created_at).getTime()) / 1000;
      if (lastRun.status !== "completed" || ageSec < COOLDOWN_SECONDS) {
        return json(
          { ok: false, reason: "cooldown", retryAfterSec: Math.ceil(COOLDOWN_SECONDS - ageSec) },
          429,
          cors
        );
      }
    }

    const dispatchRes = await fetch(
      `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${WORKFLOW}/dispatches`,
      {
        method: "POST",
        headers: { ...ghHeaders, "Content-Type": "application/json" },
        body: JSON.stringify({ ref: "main" }),
      }
    );

    if (dispatchRes.status !== 204) {
      const detail = await dispatchRes.text();
      return json({ ok: false, reason: "dispatch_failed", detail }, 502, cors);
    }

    return json({ ok: true }, 200, cors);
  },
};

function json(body, status, extraHeaders) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...extraHeaders, "Content-Type": "application/json" },
  });
}
