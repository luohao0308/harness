import http from "k6/http";
import { check, sleep } from "k6";

const BASE_URL = __ENV.HARNESS_LOAD_BASE_URL || "http://127.0.0.1:8000";
const TOKEN = __ENV.HARNESS_LOAD_TOKEN || "dev-engineer-token";

export const options = {
  scenarios: {
    mixed_workflow: {
      executor: "constant-vus",
      vus: Number(__ENV.HARNESS_LOAD_VUS || 100),
      duration: __ENV.HARNESS_LOAD_DURATION || "5m",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    "http_req_duration{endpoint:list}": ["p(50)<100", "p(99)<500"],
  },
};

const headers = {
  Authorization: `Bearer ${TOKEN}`,
  "Content-Type": "application/json",
};

export default function () {
  const listAgents = http.get(`${BASE_URL}/api/agents?limit=20`, {
    headers,
    tags: { endpoint: "list" },
  });
  check(listAgents, {
    "agents list ok": (response) => response.status === 200,
  });

  const listRuns = http.get(`${BASE_URL}/api/agents/runs?limit=20`, {
    headers,
    tags: { endpoint: "list" },
  });
  check(listRuns, {
    "runs list ok": (response) => response.status === 200,
  });

  const cost = http.get(`${BASE_URL}/api/observability/cost-rollup?window=30d&group_by=agent`, {
    headers,
    tags: { endpoint: "cost" },
  });
  check(cost, {
    "cost rollup ok": (response) => response.status === 200,
  });

  if (__VU % 10 === 0) {
    const suffix = `${__VU}-${__ITER}-${Date.now()}`;
    const createAgent = http.post(
      `${BASE_URL}/api/agents`,
      JSON.stringify({
        id: `load-agent-${suffix}`.slice(0, 64),
        name: `Load Agent ${suffix}`,
        description: "Created by the P8 k6 baseline.",
        role: "researcher",
        model_provider: "default",
        model_name: "default",
        system_prompt: "Plan, execute, and report concise evidence.",
        tools_json: ["read_file"],
        routing_tags: ["load"],
        max_parallel_assignments: 1,
      }),
      { headers, tags: { endpoint: "create_agent" } },
    );
    check(createAgent, {
      "agent create accepted": (response) => response.status === 201 || response.status === 409,
    });
  }

  sleep(1);
}
