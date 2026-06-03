import http from "k6/http";
import { check, sleep } from "k6";

const BASE_URL = __ENV.HARNESS_LOAD_BASE_URL || "http://127.0.0.1:8000";
const TOKEN = __ENV.HARNESS_LOAD_TOKEN || "dev-engineer-token";

export const options = {
  scenarios: {
    spike: {
      executor: "ramping-vus",
      stages: [
        { duration: "30s", target: 500 },
        { duration: "1m", target: 500 },
        { duration: "30s", target: 0 },
      ],
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.05"],
    "http_req_duration{endpoint:list}": ["p(99)<1000"],
  },
};

const headers = { Authorization: `Bearer ${TOKEN}` };

export default function () {
  const agents = http.get(`${BASE_URL}/api/agents?limit=10`, {
    headers,
    tags: { endpoint: "list" },
  });
  const runs = http.get(`${BASE_URL}/api/agents/runs?limit=10`, {
    headers,
    tags: { endpoint: "list" },
  });
  check(agents, { "agents list ok": (response) => response.status === 200 });
  check(runs, { "runs list ok": (response) => response.status === 200 });
  sleep(0.5);
}
