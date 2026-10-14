// k6 workload for the 1M-atom non-deep Trace production gate.
//
// Run only against a seeded staging workspace and record the generated summary
// in release evidence. Deep navigation is intentionally excluded: it is a
// separately queued workload with its own 90-second p95 gate.
import http from 'k6/http';
import { check, sleep } from 'k6';

const baseUrl = __ENV.TRACE_BASE_URL;
const workspace = __ENV.TRACE_WORKSPACE_ID;
const apiKey = __ENV.TRACE_API_KEY;

export const options = {
  scenarios: {
    non_deep_mix: {
      executor: 'constant-arrival-rate',
      rate: Number(__ENV.TRACE_QPS || 500),
      timeUnit: '1s',
      duration: __ENV.TRACE_DURATION || '15m',
      preAllocatedVUs: Number(__ENV.TRACE_PREALLOCATED_VUS || 200),
      maxVUs: Number(__ENV.TRACE_MAX_VUS || 1000),
    },
  },
  thresholds: {
    'http_req_failed{profile:fast}': ['rate<0.001'],
    'http_req_duration{profile:fast}': ['p(95)<=2000'],
    'http_req_duration{profile:standard}': ['p(95)<=5000'],
    'http_req_duration{profile:graph}': ['p(95)<=5000'],
    'http_req_duration{profile:hierarchy}': ['p(95)<=5000'],
  },
};

function profile() {
  const sample = Math.random();
  if (sample < 0.70) return ['fast', 'fast retrieval evidence'];
  if (sample < 0.90) return ['standard', 'standard retrieval evidence'];
  if (sample < 0.95) return ['graph', 'graph dependency evidence'];
  return ['hierarchy', 'hierarchy navigation evidence'];
}

export default function () {
  if (!baseUrl || !workspace || !apiKey) {
    throw new Error('TRACE_BASE_URL, TRACE_WORKSPACE_ID, and TRACE_API_KEY are required');
  }
  const [mode, query] = profile();
  const body = JSON.stringify({
    workspace_id: workspace,
    query,
    retrieval_profile: mode === 'fast' ? 'hybrid' : mode,
    retrieval_budget: { mode, allow_deep_escalation: false },
  });
  const response = http.post(`${baseUrl}/v2/queries`, body, {
    headers: { 'Content-Type': 'application/json', 'X-API-Key': apiKey },
    tags: { profile: mode === 'fast' ? 'fast' : mode },
  });
  check(response, { 'query returned evidence contract': (result) => result.status === 200 });
  sleep(0.001);
}
