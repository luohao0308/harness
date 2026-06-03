import http from "k6/http";
import { check, sleep } from "k6";

const BASE_URL = __ENV.HARNESS_LOAD_BASE_URL || "http://127.0.0.1:8000";
const TOKEN = __ENV.HARNESS_LOAD_TOKEN || "dev-engineer-token";

export const options = {
  scenarios: {
    soak: {
      executor: "constant-vus",
      vus: Number(__ENV.HARNESS_LOAD_SOAK_VUS || 50),
      duration: __ENV.HARNESS_LOAD_SOAK_DURATION || "30m",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    "http_req_duration{endpoint:list}": ["p(99)<750"],
  },
};

const headers = { Authorization: `Bearer ${TOKEN}` };

export default function () {
  const agents = http.get(`${BASE_URL}/api/agents?limit=20`, {
    headers,
    tags: { endpoint: "list" },
  });
  const runs = http.get(`${BASE_URL}/api/agents/runs?limit=20`, {
    headers,
    tags: { endpoint: "list" },
  });
  const evals = http.get(`${BASE_URL}/api/evals/datasets?limit=20`, {
    headers,
    tags: { endpoint: "list" },
  });
  check(agents, { "agents list ok": (response) => response.status === 200 });
  check(runs, { "runs list ok": (response) => response.status === 200 });
  check(evals, { "eval datasets list ok": (response) => response.status === 200 });
  sleep(2);
}
