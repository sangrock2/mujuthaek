// 테스트 종류별 부하 모양과 합격 기준. 문서 「무주택자들 성능 테스트 계획」의 표와 같은 값이에요.
// 개선 전후를 비교하려면 이 파일을 바꾸지 않아야 해요 (바꾸면 run.sh가 meta.json에 git SHA로 남겨요)

export const BASE_URL = __ENV.BASE_URL || 'http://3.37.131.73';
export const TEST = __ENV.TEST || 'smoke';

// API 종류별 응답 시간 목표(ms): 조회 lookup · 목록·검색 search · 판정 judge
const LATENCY = {
  lookup: ['p(95)<200', 'p(99)<500'],
  search: ['p(95)<500', 'p(99)<1000'],
  judge: ['p(95)<1000', 'p(99)<2000'],
};

// 한계를 찾는 테스트는 기준을 넘으면 1분 더 지켜본 뒤 멈춰요(넘은 단계가 한계)
function latency(abort) {
  const t = {};
  for (const [type, rules] of Object.entries(LATENCY)) {
    t[`http_req_duration{type:${type}}`] = abort
      ? rules.map((threshold) => ({ threshold, abortOnFail: true, delayAbortEval: '1m' }))
      : rules;
  }
  return t;
}

const errorRate = (rate, abort) =>
  abort ? [{ threshold: `rate<${rate}`, abortOnFail: true, delayAbortEval: '1m' }] : [`rate<${rate}`];

const vus = (stages) => ({ executor: 'ramping-vus', startVUs: 0, stages, gracefulRampDown: '30s' });

// 50 → 100 → 200 → 400 → 700 → 1,000명, 단계마다 3분(30초 올리고 2분 30초 유지)
const stressStages = [50, 100, 200, 400, 700, 1000].flatMap((target) => [
  { duration: '30s', target },
  { duration: '2m30s', target },
]);

// 초당 20건에서 2분마다 20건씩, 최대 초당 1,000건(그 전에 기준을 넘어 멈춰요)
const breakpointStages = Array.from({ length: 50 }, (_, i) => ({ duration: '2m', target: 20 * (i + 1) }));

export const PROFILES = {
  smoke: {
    scenario: { executor: 'constant-vus', vus: 2, duration: '1m' },
    thresholds: { ...latency(false), http_req_failed: ['rate==0'], server_errors: ['count==0'] },
  },
  load: {
    scenario: vus([
      { duration: '2m', target: 100 },
      { duration: '15m', target: 100 },
      { duration: '1m', target: 0 },
    ]),
    thresholds: { ...latency(false), http_req_failed: errorRate(0.01), server_errors: ['count==0'] },
  },
  soak: {
    scenario: vus([
      { duration: '2m', target: 50 },
      { duration: '60m', target: 50 },
      { duration: '1m', target: 0 },
    ]),
    thresholds: { ...latency(false), http_req_failed: errorRate(0.01), server_errors: ['count==0'] },
  },
  stress: {
    scenario: vus(stressStages),
    thresholds: { ...latency(true), http_req_failed: errorRate(0.01, true) },
  },
  // 쉬는 시간 없이 요청 수로 밀어요. 반복 한 번 = 요청 한 건이라 초당 반복 수가 곧 RPS예요
  breakpoint: {
    scenario: {
      executor: 'ramping-arrival-rate',
      startRate: 20,
      timeUnit: '1s',
      preAllocatedVUs: 100,
      maxVUs: 1500,
      stages: breakpointStages,
    },
    thresholds: { ...latency(true), http_req_failed: errorRate(0.01, true) },
  },
  spike: {
    scenario: vus([
      { duration: '30s', target: 20 },
      { duration: '10s', target: 500 },
      { duration: '1m', target: 500 },
      { duration: '10s', target: 20 },
      { duration: '2m', target: 20 },
    ]),
    thresholds: { http_req_failed: errorRate(0.05) },
  },
};
