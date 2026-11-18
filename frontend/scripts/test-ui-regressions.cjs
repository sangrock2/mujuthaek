/* eslint-disable @typescript-eslint/no-require-imports -- isolated CommonJS TypeScript test loader */
/* Run with node scripts/test-ui-regressions.cjs. Uses the existing TypeScript compiler. */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const Module = require("node:module");
const ts = require("typescript");
const resolve = Module._resolveFilename;
Module._resolveFilename = function (name, parent, ...args) {
  return resolve.call(
    this,
    name.startsWith("@/") ? path.join(__dirname, "../src", name.slice(2)) : name,
    parent,
    ...args,
  );
};
for (const ext of [".ts", ".tsx"]) {
  require.extensions[ext] = (module, filename) => {
    const { outputText } = ts.transpileModule(fs.readFileSync(filename, "utf8"), {
      // 파일 이름을 줘야 .ts의 <T>(…) 제네릭을 JSX로 읽지 않아요 (api/client.ts를 불러올 수 있게)
      fileName: filename,
      compilerOptions: {
        // tsconfig와 같은 대상. 기본값(ES5)이면 class ApiError extends Error의 instanceof가 깨져요
        target: ts.ScriptTarget.ES2017,
        module: ts.ModuleKind.CommonJS,
        jsx: ts.JsxEmit.ReactJSX,
        esModuleInterop: true,
      },
    });
    module._compile(outputText, filename);
  };
}

const { defaultDevice } = require("../src/features/profile/defaults.ts");
const { toApplicant } = require("../src/features/conditions/applicant.ts");
const { migrateDevice } = require("../src/features/conditions/store.ts");
const { birthProblem } = require("../src/features/profile/components/BirthField.tsx");
const { formatWon } = require("../src/shared/lib/money.ts");
const { browserApiOrigin, secureApiOrigin } = require("../src/shared/lib/api/origin.ts");
assert.equal(browserApiOrigin(undefined, "https://api.example.com", true), "");
assert.equal(browserApiOrigin("", "https://api.example.com", true), "");
assert.equal(browserApiOrigin("http://127.0.0.1:18080", "", false), "http://127.0.0.1:18080");
assert.throws(() => browserApiOrigin("https://old.vercel.app", "https://api.example.com", true));
assert.equal(secureApiOrigin("https://api.example.com/", true), "https://api.example.com");
assert.equal(secureApiOrigin("http://127.0.0.1:18080"), "http://127.0.0.1:18080");
assert.equal(secureApiOrigin(undefined, true), "");
for (const origin of [
  "http://api.example.com",
  "http://3.37.131.73",
  "ftp://api.example.com",
  "https://user:pass@api.example.com",
  "https://api.example.com/path",
  "https://api.example.com?key=value",
]) {
  assert.throws(() => secureApiOrigin(origin));
}
assert.throws(() => secureApiOrigin("http://localhost:8080", true));
assert.throws(() => secureApiOrigin("https://localhost", true));
const empty = defaultDevice({ defaultPriorities: [] });
const request = (device, session = null) =>
  JSON.parse(JSON.stringify(toApplicant(device, session)));

for (const key of ["head", "marry", "homelessPeriod", "bankbookPeriod", "householdSize"])
  assert.equal(empty[key], "");
assert.equal(empty.kids, null);
const untouched = request(empty);
for (const key of [
  "householdHead",
  "marital",
  "homeOwner",
  "homelessYears",
  "householdSize",
  "children",
  "subscription",
])
  assert.equal(key in untouched, false, `미입력 ${key}는 요청에서 제외`);
assert.equal("targetGroups" in untouched, false);
const emptySession = {
  income: "3200",
  asset: "",
  assetUnknown: false,
  available: "",
  rankChecks: [],
};
const withoutSize = JSON.parse(
  JSON.stringify(
    toApplicant(empty, emptySession, {
      year: 2026,
      medianIncomeMonthlyWon: { 1: 2_000_000 },
      assetCutsWon: [],
      carCutsWon: [],
    }),
  ),
);
for (const key of ["income", "welfareStatuses", "rankChecks"])
  assert.equal(key in withoutSize, false);
const explicit = request({
  ...empty,
  head: "member",
  marry: "single",
  kids: 0,
  householdSize: "1명",
  homelessPeriod: "1년 미만",
  bankbookPeriod: "없어요",
});
assert.equal(explicit.householdHead, false);
assert.equal(explicit.marital, "SINGLE");
assert.equal(explicit.children, 0);
assert.equal(explicit.householdSize, 1);
assert.equal(explicit.homeOwner, false);
assert.equal(explicit.homelessYears, "LT_1");
assert.equal(explicit.subscription.months, "NONE");
assert.equal(request({ ...empty, homelessPeriod: "집이 있어요" }).homeOwner, true);
const legacy = {
  ...empty,
  selectionVersion: undefined,
  head: "head",
  marry: "single",
  kids: 0,
  householdSize: "1명",
  homelessPeriod: "3년 이상 5년 미만",
};
const migrated = migrateDevice(legacy);
assert.equal(migrated.needsReconfirmation, true);
for (const key of ["head", "marry", "householdSize", "homelessPeriod"])
  assert.equal(migrated[key], "");
assert.equal(request(migrated).homeOwner, undefined);
const confirmed = { ...empty, head: "head", kids: 0, householdSize: "2명" };
assert.deepEqual(migrateDevice(confirmed), confirmed);
assert.equal(birthProblem(""), null);
assert.equal(birthProblem("2000.02.29"), null);
assert.ok(birthProblem("2001.02.29"));
assert.ok(birthProblem("1997.."));
assert.ok(birthProblem("2999.01.01"));
for (const [won, text] of [
  [0, "0원"],
  [240_000_000, "2억 4,000만 원"],
  [18_551_000, "1,855만 1,000원"],
  [100_000_000, "1억 원"],
  [-15_000, "−1만 5,000원"],
  [999, "999원"],
])
  assert.equal(formatWon(won), text);
const {
  koreaDay,
  sortedTasks,
  taskCounts,
  taskDueLabel,
} = require("../src/features/preparations/plan.ts");
const task = (id, dueOn, done = false) => ({
  id,
  title: id,
  dueOn,
  done,
  createdAt: "2026-11-01T00:00:00Z",
});
const taskRows = [
  task("no-date", null),
  task("today", "2026-11-12"),
  task("done", "2026-11-01", true),
  task("late", "2026-11-11"),
  task("future", "2026-11-15"),
].map((row, index) => ({ ...row, createdAt: `2026-11-01T00:00:0${index}Z` }));
assert.equal(koreaDay(new Date("2026-11-11T14:59:59Z")), "2026-11-11");
assert.equal(koreaDay(new Date("2026-11-11T15:00:00Z")), "2026-11-12");
assert.deepEqual(
  sortedTasks(taskRows).map((t) => t.id),
  ["no-date", "today", "done", "late", "future"],
);
assert.deepEqual(
  sortedTasks(taskRows, "due").map((t) => t.id),
  ["done", "late", "today", "future", "no-date"],
);
assert.deepEqual(taskCounts(taskRows, "2026-11-12"), {
  total: 5,
  done: 1,
  open: 4,
  overdue: 1,
  today: 1,
});
assert.equal(taskDueLabel(taskRows[0], "2026-11-12"), "기한 없음");
assert.equal(taskDueLabel(taskRows[1], "2026-11-12"), "오늘까지");
assert.match(taskDueLabel(taskRows[3], "2026-11-12"), /^기한 지남/);
assert.equal(taskRows[0].id, "no-date", "정렬은 입력 배열을 변경하지 않음");

// ── 외부 링크 주소 검사 (2026-11-16 보안 감사 L-4) ─────────────────────────
const { safeExternalUrl, safeAppPath } = require("../src/shared/lib/safeUrl.ts");
const ch = (code) => String.fromCharCode(code);
const backslash = ch(92);
for (const [input, output] of [
  [
    "https://www.myhome.go.kr/hws/portal/sch/a.do?pblancId=1",
    "https://www.myhome.go.kr/hws/portal/sch/a.do?pblancId=1",
  ],
  ["http://www.lh.or.kr/", "http://www.lh.or.kr/"],
  ["http://www.lh.or.kr", "http://www.lh.or.kr/"],
  ["  https://www.gov.kr/portal  ", "https://www.gov.kr/portal"],
  ["HTTPS://WWW.BOKJIRO.GO.KR/x", "https://www.bokjiro.go.kr/x"],
])
  assert.equal(safeExternalUrl(input), output, `허용: ${input}`);
for (const bad of [
  "javascript:alert(1)",
  "JaVaScRiPt:alert(1)",
  " javascript:alert(1)",
  `java${ch(9)}script:alert(1)`,
  "data:text/html,<script>alert(1)</script>",
  `search-ms:query=x&crumb=location:${backslash}${backslash}evil${backslash}share`,
  "ms-settings:privacy",
  "ms-msdt:/id PCWDiagnostic",
  "intent://evil#Intent;scheme=https;end",
  "vbscript:msgbox(1)",
  "file:///C:/Windows/win.ini",
  "//evil.example/x",
  "/notices/1",
  "www.gov.kr",
  "https:///evil.example",
  "https:evil.example",
  "https://user:pass@evil.example/",
  "https://www.gov.kr@evil.example/",
  `https://www.gov.kr${backslash}@evil.example/`,
  "https://www.gov.kr/a b",
  `https://www.gov.kr/${ch(0)}`,
  `https://www.gov.kr/${ch(0x200b)}x`,
  `https://www.gov.kr/${ch(0x202e)}fdp.exe`,
  `https://www.gov.kr/${ch(10)}x`,
  `https://www.gov.kr/${"a".repeat(2100)}`,
  "",
  null,
  undefined,
  42,
  {},
])
  assert.equal(safeExternalUrl(bad), null, `거부: ${String(bad).slice(0, 40)}`);
for (const ok of ["/notices/abc", "/me?tab=reports", "/api/v1/notices/1/files/2"])
  assert.equal(safeAppPath(ok), ok);
for (const bad of [
  "//evil.example",
  `/${backslash}evil.example`,
  "https://evil.example",
  "notices/1",
  `/${ch(9)}/evil.example`,
  "/a b",
  "",
  null,
])
  assert.equal(safeAppPath(bad), null, `앱 경로 거부: ${String(bad)}`);

const { safeNext, routes } = require("../src/shared/lib/routes.ts");
assert.equal(safeNext("/homes?region=11#results"), "/homes?region=11#results");
for (const next of [
  "/\t/attacker.invalid",
  "/\n/attacker.invalid",
  "/\r/attacker.invalid",
  "//attacker.invalid",
  "/\\attacker.invalid",
  "https://attacker.invalid",
  "/x\u0000",
])
  assert.equal(safeNext(next), null, "돌아갈 경로도 URL 정규화 전에 제어 문자를 거절");
for (const encoded of [
  "%2F%09%2Fattacker.invalid",
  "%2F%0A%2Fattacker.invalid",
  "%2F%0D%2Fattacker.invalid",
])
  assert.equal(safeNext(new URLSearchParams(`next=${encoded}`).get("next")), null);
assert.equal(routes.notice("a/b?c"), "/notices/a%2Fb%3Fc");
assert.equal(routes.benefit("a#b"), "/benefits/a%23b");
assert.equal(routes.space("a/b"), "/business/spaces/a%2Fb");
for (const id of [".", "..", ""]) assert.throws(() => routes.preparation(id));

// ── API 경로 조립 (2026-11-16 보안 감사 L-6) ─────────────────────────────
const { apiPath, isUuid, pathSegment } = require("../src/shared/lib/api/path.ts");
const traversal = decodeURIComponent("..%2Fusers%3Fsize%3D1%26q%3D");
assert.equal(isUuid(traversal), false, "감사 PoC의 job 값은 UUID가 아님");
assert.equal(isUuid("0190f3c4-8d5e-7a6b-9c1d-2e3f4a5b6c7d"), true);
assert.equal(isUuid("0190F3C4-8D5E-7A6B-9C1D-2E3F4A5B6C7D"), true);
for (const bad of [
  null,
  undefined,
  "",
  "r2",
  "demo-job-n1",
  " 0190f3c4-8d5e-7a6b-9c1d-2e3f4a5b6c7d",
])
  assert.equal(isUuid(bad), false);
const tracePath = apiPath`/api/admin/reviews/${traversal}/trace`;
assert.equal(tracePath, "/api/admin/reviews/..%2Fusers%3Fsize%3D1%26q%3D/trace");
assert.equal(new URL(tracePath, "https://api.test").pathname, tracePath, "다른 API로 새지 않음");
for (const bad of ["", ".", ".."]) assert.throws(() => pathSegment(bad));
assert.equal(
  new URL(apiPath`/api/admin/users/${"%2e%2e"}/role`, "https://api.test").pathname,
  "/api/admin/users/%252e%252e/role",
);
assert.equal(
  apiPath`/api/admin/criteria/MEDIAN_INCOME/${2027}`,
  "/api/admin/criteria/MEDIAN_INCOME/2027",
);

// ── 기기 저장소 (2026-11-16 보안 감사 L-3) ───────────────────────────────
class MemoryStorage {
  constructor() {
    this.map = new Map();
  }
  get length() {
    return this.map.size;
  }
  key(i) {
    return [...this.map.keys()][i] ?? null;
  }
  getItem(k) {
    return this.map.has(k) ? this.map.get(k) : null;
  }
  setItem(k, v) {
    this.map.set(k, String(v));
  }
  removeItem(k) {
    this.map.delete(k);
  }
}
const events = new EventTarget();
global.window = {
  localStorage: new MemoryStorage(),
  sessionStorage: new MemoryStorage(),
  addEventListener: events.addEventListener.bind(events),
  removeEventListener: events.removeEventListener.bind(events),
  dispatchEvent: events.dispatchEvent.bind(events),
};
const local = window.localStorage;
const tab = window.sessionStorage;

// 주거·사업 정보의 삭제·저장 방식·보관 기간 경계는 함께 적용해요.
const conditionStore = require("../src/features/conditions/store.ts");
const bizProfile = require("../src/features/business/profile.ts");
const retention = require("../src/shared/lib/deviceRetention.ts");
local.removeItem("mujuthaek:save-on-device");
conditionStore.saveConditions(empty, emptySession);
bizProfile.saveBizProfile(
  { ...bizProfile.emptyBizProfile, industry: "SOFTWARE" },
  {
    revenue: "1234",
    restrictions: ["TAX_ARREARS"],
  },
);
assert.equal(JSON.parse(local.getItem("mujuthaek:business:v1")).data.industry, "SOFTWARE");
conditionStore.setSaveOnDevice(false);
assert.equal(local.getItem("mujuthaek:business:v1"), null, "기기 저장을 끄면 사업 사본도 지움");
assert.equal(JSON.parse(tab.getItem("mujuthaek:business:device-session")).industry, "SOFTWARE");
assert.equal(tab.getItem("mujuthaek:business:revenue"), "1234", "전환 중 매출은 탭에만 유지");
conditionStore.setSaveOnDevice(true);
assert.equal(tab.getItem("mujuthaek:business:device-session"), null);
assert.equal(JSON.parse(local.getItem("mujuthaek:business:v1")).data.industry, "SOFTWARE");
conditionStore.clearConditions();
for (const [storage, key] of [
  [local, "mujuthaek:conditions:v1"],
  [local, "mujuthaek:business:v1"],
  [tab, "mujuthaek:conditions:session"],
  [tab, "mujuthaek:business:device-session"],
  [tab, "mujuthaek:business:revenue"],
  [tab, "mujuthaek:business:restrictions"],
])
  assert.equal(storage.getItem(key), null, `전체 조건 삭제: ${key}`);
for (const savedAt of [Date.now() - retention.DEVICE_DATA_TTL_MS, Date.now() + 60_000, "invalid"]) {
  local.setItem(
    "mujuthaek:business:v1",
    JSON.stringify({ savedAt, data: bizProfile.emptyBizProfile }),
  );
  bizProfile.moveBizProfileStorage(false);
  assert.equal(local.getItem("mujuthaek:business:v1"), null);
  assert.equal(
    tab.getItem("mujuthaek:business:device-session"),
    null,
    "만료/미래 저장값은 옮기지 않음",
  );
}
local.setItem("mujuthaek:business:v1", JSON.stringify(bizProfile.emptyBizProfile));
bizProfile.moveBizProfileStorage(false);
assert.equal(local.getItem("mujuthaek:business:v1"), null, "저장 시각 없는 예전 사업 값도 제거");
assert.equal(tab.getItem("mujuthaek:business:device-session"), null);

const recent = require("../src/features/search/recent.ts");
const at = 1_800_000_000_000;
assert.deepEqual(
  recent.parseRecent(JSON.stringify(["예전", "글자 목록"]), at),
  [],
  "예전 모양은 저장 시각을 몰라 버림",
);
assert.deepEqual(recent.parseRecent("{not json", at), []);
assert.deepEqual(
  recent
    .parseRecent(
      JSON.stringify([
        { q: "청년", at: at - recent.RECENT_TTL_MS },
        { q: "신혼", at: at - 1000 },
      ]),
      at,
    )
    .map((e) => e.q),
  ["신혼"],
  "30일 지난 검색어는 버림",
);
let entries = [];
for (let i = 0; i < 12; i++) entries = recent.addRecent(entries, `검색 ${i}`, at + i);
assert.equal(entries.length, recent.RECENT_MAX);
assert.equal(entries[0].q, "검색 11");
entries = recent.addRecent(entries, "검색 5", at + 20);
assert.equal(entries[0].q, "검색 5");
assert.equal(entries.filter((e) => e.q === "검색 5").length, 1);
assert.equal(recent.addRecent(entries, "   ", at), entries);
assert.equal(recent.addRecent(entries, "가".repeat(recent.RECENT_TEXT_MAX + 1), at), entries);
local.setItem("mujuthaek.search.recent", JSON.stringify(["예전 검색어"]));
assert.deepEqual(recent.readRecent(at), []);
assert.equal(local.getItem("mujuthaek.search.recent"), null, "예전 모양은 읽을 때 지움");
recent.rememberRecent("행복주택", at);
assert.deepEqual(recent.readRecent(at + 1000), ["행복주택"]);
assert.deepEqual(recent.readRecent(at + recent.RECENT_TTL_MS), []);
assert.equal(local.getItem("mujuthaek.search.recent"), null, "만료된 검색어도 읽을 때 지움");
let recentCleared = 0;
const stopRecent = recent.subscribeRecent(() => recentCleared++);
recent.rememberRecent("행복주택", at);
recent.clearRecentSearches();
stopRecent();
assert.deepEqual(recent.readRecent(at), []);
assert.equal(recentCleared, 1, "지우면 검색 화면에 알림");

const device = require("../src/features/auth/deviceData.ts");
const personalLocal = [
  "mujuthaek:conditions:v1",
  "mujuthaek:business:v1",
  "mujuthaek.search.recent",
  "mujuthaek:chat-nudge:notice-1",
];
const personalTab = [
  "mujuthaek:conditions:session",
  "mujuthaek:conditions:device-session",
  "mujuthaek:business:revenue",
  "mujuthaek:business:restrictions",
  "mujuthaek:business:device-session",
];
const seedDevice = () => {
  for (const key of personalLocal) local.setItem(key, "{}");
  local.setItem("mujuthaek.search.recent", JSON.stringify([{ q: "청년 월세", at: Date.now() }]));
  for (const key of personalTab) tab.setItem(key, "{}");
  local.setItem("mujuthaek:analytics-consent", "denied");
  local.setItem("mujuthaek:save-on-device", "false");
  tab.setItem("mujuthaek:demo-notice-hidden", "1");
  local.setItem("other-site-key", "keep");
};
const expectWiped = (why) => {
  for (const key of personalLocal) assert.equal(local.getItem(key), null, `${why}: ${key}`);
  for (const key of personalTab) assert.equal(tab.getItem(key), null, `${why}: ${key}`);
  assert.equal(local.getItem("mujuthaek:analytics-consent"), "denied", `${why}: 통계 동의는 둠`);
  assert.equal(local.getItem("mujuthaek:save-on-device"), "false", `${why}: 저장 방식 설정은 둠`);
  assert.equal(tab.getItem("mujuthaek:demo-notice-hidden"), "1", `${why}: 시연 안내 닫음은 둠`);
  assert.equal(local.getItem("other-site-key"), "keep", `${why}: 우리 키가 아니면 둠`);
};
seedDevice();
device.claimDeviceData("user-a");
assert.notEqual(
  local.getItem("mujuthaek:conditions:v1"),
  null,
  "로그인 전에 입력한 값은 첫 계정이 이어 씀",
);
assert.equal(local.getItem("mujuthaek:owner"), device.ownerMark("user-a"));
assert.equal(
  local.getItem("mujuthaek:owner").includes("user-a"),
  false,
  "계정 ID를 그대로 두지 않음",
);
assert.notEqual(device.ownerMark("user-a"), device.ownerMark("user-b"));
device.claimDeviceData("user-a");
assert.notEqual(local.getItem("mujuthaek:conditions:v1"), null, "같은 계정이면 그대로");
device.claimDeviceData("user-b");
expectWiped("다른 계정으로 로그인");
assert.equal(local.getItem("mujuthaek:owner"), device.ownerMark("user-b"));
seedDevice();
device.forgetDeviceData();
expectWiped("로그아웃");
assert.equal(local.getItem("mujuthaek:owner"), null, "로그아웃하면 주인 표시도 지움");
assert.equal(device.consumeWithdrawalMark(at), false, "탈퇴를 시작하지 않은 탭");
device.markWithdrawalStarted(at);
assert.equal(device.consumeWithdrawalMark(at + 60_000), true);
assert.equal(device.consumeWithdrawalMark(at + 60_000), false, "한 번만 씀");
device.markWithdrawalStarted(at);
assert.equal(
  device.consumeWithdrawalMark(at + 2 * 60 * 60 * 1000),
  false,
  "오래된 표시는 믿지 않음",
);

// ── 가입 필수 동의 (2026-11-16 보안 감사 L-2) ────────────────────────────
const session = require("../src/features/auth/session.ts");
assert.equal(session.isMember(null), false);
assert.equal(session.isMember(undefined), false);
assert.equal(
  session.isMember({ id: "a", termsAgreed: false }),
  false,
  "동의 전이면 내 정보 API를 부르지 않음",
);
assert.equal(session.isMember({ id: "a", termsAgreed: true }), true);
assert.equal(session.isMember({ id: "a" }), true, "동의 칸이 없는 예전 응답은 막지 않음");
for (const path of [
  "/signup",
  "/terms",
  "/privacy",
  "/legal",
  "/legal/privacy/1.1",
  "/auth/callback",
  "/withdrawn",
  "/email/unsubscribe",
  "/offline",
])
  assert.equal(session.isTermsFreePath(path), true, `동의 전에도 머무름: ${path}`);
for (const path of [
  "/",
  "/home",
  "/me",
  "/alerts",
  "/signupx",
  "/termsx",
  "/email/verify",
  "/admin",
])
  assert.equal(session.isTermsFreePath(path), false, `동의 화면으로 보냄: ${path}`);

// ── 보안 헤더·CSP (2026-11-16 보안 감사 4장) ──────────────────────────────
const headersLib = require("../src/shared/lib/securityHeaders.ts");
const csp = (options) =>
  Object.fromEntries(
    headersLib
      .contentSecurityPolicy({
        dev: false,
        apiOrigin: "",
        analytics: false,
        kakaoMap: false,
        ...options,
      })
      .split("; ")
      .map((part) => {
        const [name, ...sources] = part.split(" ");
        return [name, sources];
      }),
  );
const base = csp({});
assert.deepEqual(base["connect-src"], ["'self'"], "기본은 이 사이트로만 요청");
assert.deepEqual(
  base["script-src"],
  ["'self'", "'unsafe-inline'"],
  "운영 빌드는 eval·외부 스크립트 없음",
);
assert.deepEqual(base["form-action"], ["'self'"]);
assert.deepEqual(base["default-src"], ["'self'"]);
assert.deepEqual(base["object-src"], ["'none'"]);
assert.deepEqual(base["base-uri"], ["'none'"]);
assert.deepEqual(base["frame-ancestors"], ["'none'"]);
assert.equal(
  base["img-src"].some((s) => s.includes("*") && !s.includes(".")),
  false,
  "이미지도 아무 호스트나 받지 않음",
);
assert.ok(csp({ dev: true })["script-src"].includes("'unsafe-eval'"), "개발 서버만 eval 허용");
assert.deepEqual(csp({ apiOrigin: "http://127.0.0.1:18080" })["connect-src"], [
  "'self'",
  "http://127.0.0.1:18080",
]);
const withThirdParties = csp({ analytics: true, kakaoMap: true });
assert.ok(withThirdParties["script-src"].includes("https://www.googletagmanager.com"));
assert.equal(withThirdParties["script-src"].includes("https://*.googletagmanager.com"), false);
assert.ok(withThirdParties["connect-src"].includes("https://*.google-analytics.com"));
assert.ok(new Set(withThirdParties["script-src"]).has("dapi.kakao.com"));
assert.ok(withThirdParties["img-src"].includes("*.daumcdn.net"));
assert.equal(withThirdParties["script-src"].includes("'unsafe-eval'"), false);
for (const source of [...base["script-src"], ...base["connect-src"]])
  assert.equal(/google|kakao|daum/.test(source), false, "GA·카카오를 끄면 호스트도 넣지 않음");
const headerMap = Object.fromEntries(
  headersLib
    .securityHeaders({ dev: false, apiOrigin: "", analytics: false, kakaoMap: false })
    .map((h) => [h.key, h.value]),
);
assert.equal(headerMap["Cross-Origin-Opener-Policy"], "same-origin");
assert.equal(headerMap["Cross-Origin-Resource-Policy"], "same-origin");
for (const feature of ["camera=()", "microphone=()", "geolocation=()", "payment=()"])
  assert.ok(headerMap["Permissions-Policy"].includes(feature), feature);
assert.equal(
  headersLib.serviceWorkerPolicy(""),
  "default-src 'self'; script-src 'self'; connect-src 'self'",
);
assert.equal(require("../next.config.ts").default.experimental.sri.algorithm, "sha384");
assert.equal(headersLib.safeGaId("G-ABC123XYZ"), "G-ABC123XYZ");
for (const bad of ["", undefined, "UA-1234-1", "G-ABC');alert(1);//", "g-abc123", "G-ABC 123"])
  assert.equal(headersLib.safeGaId(bad), "", `GA ID 거부: ${String(bad)}`);

// ── 서비스 워커 API 주소 (2026-11-16 보안 감사 4장) ──────────────────────
const vm = require("node:vm");
const workerApiBase = (href) => {
  const context = vm.createContext({
    URL,
    self: { location: new URL(href), addEventListener() {} },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../public/sw.js"), "utf8"), context);
  return context.API_BASE ?? vm.runInContext("API_BASE", context);
};
assert.equal(workerApiBase("https://app.test/sw.js?api="), "https://app.test", "운영: 같은 주소");
assert.equal(workerApiBase("https://app.test/sw.js"), "https://app.test");
assert.equal(
  workerApiBase(`https://app.test/sw.js?api=${encodeURIComponent("https://evil.test")}`),
  "https://app.test",
  "다른 출처는 받지 않음",
);
assert.equal(
  workerApiBase(`https://app.test/sw.js?api=${encodeURIComponent("http://localhost:8080")}`),
  "https://app.test",
  "운영 워커는 로컬 주소도 받지 않음",
);
assert.equal(
  workerApiBase(`http://localhost:3000/sw.js?api=${encodeURIComponent("http://localhost:8080")}`),
  "http://localhost:8080",
  "로컬 개발: 로컬 API",
);
assert.equal(
  workerApiBase(`http://127.0.0.1:13000/sw.js?api=${encodeURIComponent("https://evil.test")}`),
  "http://127.0.0.1:13000",
  "로컬이어도 바깥 호스트는 받지 않음",
);
assert.equal(workerApiBase("https://app.test/sw.js?api=javascript:alert(1)"), "https://app.test");

// ── 경로의 ID (2026-11-16 보안 감사 4장) ─────────────────────────────────
const { endpoints } = require("../src/shared/lib/api/endpoints.ts");
assert.throws(() => endpoints.noticeDetail(".."), "「..」은 경로에 넣지 않음");
assert.throws(() => endpoints.chatMessage("."));
assert.equal(endpoints.favorite("notice", "a/b?c"), "/api/users/me/favorites/notice/a%2Fb%3Fc");
assert.equal(endpoints.noticeChatStream("n-1"), "/api/v1/notices/n-1/chat/stream");

// ── 제보 딥링크 (2026-11-16 보안 감사 4장) ───────────────────────────────
const tabs = require("../src/features/me/tabs.ts");
assert.equal(tabs.reportScreenParam("검색"), "검색");
assert.equal(tabs.reportScreenParam("관리자 승인 요청"), undefined, "목록에 없는 화면 이름은 버림");
assert.equal(tabs.reportScreenParam(null), undefined);
assert.equal(tabs.reportCodeParam("E-503"), "E-503");
for (const bad of ["", null, "a".repeat(41), "E 503", "<b>x</b>", "-E"])
  assert.equal(tabs.reportCodeParam(bad), undefined, `오류 코드 거부: ${String(bad)}`);
for (const from of tabs.reportScreens) {
  const href = new URL(tabs.reportHref({ from, code: "E-1" }), "https://app.test");
  assert.equal(
    tabs.reportScreenParam(href.searchParams.get("from")),
    from,
    "앱이 만든 링크는 그대로",
  );
}

// ── 방문 통계 동의 철회 (2026-11-16 보안 감사 4장) ───────────────────────
process.env.NEXT_PUBLIC_GA_ID = "G-TEST1234";
const cookieJar = new Map([
  ["_ga", "x"],
  ["_ga_TEST1234", "y"],
  ["theme", "dark"],
]);
global.location = { hostname: "www.app.test" };
global.document = {
  get cookie() {
    return [...cookieJar].map(([k, v]) => `${k}=${v}`).join("; ");
  },
  set cookie(value) {
    const [pair, ...attrs] = value.split(";").map((s) => s.trim());
    const [name] = pair.split("=");
    if (attrs.some((a) => a.toLowerCase().startsWith("expires=thu, 01 jan 1970")))
      cookieJar.delete(name);
  },
};
// analytics.ts는 전역 localStorage를 읽어요 (브라우저와 같게)
const storageDescriptor = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
Object.defineProperty(globalThis, "localStorage", {
  value: local,
  configurable: true,
  writable: true,
});
// 앞에서 GA ID 없이 불러온 모듈이 있으면 지우고 GA ID가 있는 상태로 다시 불러요
delete require.cache[require.resolve("../src/shared/lib/analytics.ts")];
const analytics = require("../src/shared/lib/analytics.ts");
const sent = [];
window.gtag = (...args) => sent.push(args);
analytics.writeConsent("granted");
analytics.track("judgment_run");
assert.equal(sent.length, 1, "동의하면 보냄");
analytics.writeConsent("denied");
analytics.track("judgment_run");
assert.equal(sent.length, 1, "철회하면 불러온 gtag가 있어도 보내지 않음");
assert.equal(window["ga-disable-G-TEST1234"], true, "GA 자체도 멈춤");
assert.equal(cookieJar.has("_ga") || cookieJar.has("_ga_TEST1234"), false, "GA 쿠키를 지움");
assert.equal(cookieJar.get("theme"), "dark", "다른 쿠키는 둠");
delete window.gtag;
delete global.document;
delete global.location;
local.removeItem("mujuthaek:analytics-consent");
if (storageDescriptor) Object.defineProperty(globalThis, "localStorage", storageDescriptor);
else delete globalThis.localStorage;

const client = require("../src/shared/lib/api/client.ts");
(async () => {
  let termsRequired = 0;
  const stopTerms = client.subscribeTermsRequired(() => termsRequired++);
  const problem = (status, code) => async () =>
    new Response(JSON.stringify({ status, code }), {
      status,
      headers: { "Content-Type": "application/problem+json" },
    });
  global.fetch = problem(403, "TERMS_NOT_AGREED");
  await assert.rejects(client.api.get("/api/users/me/favorites"), (e) =>
    client.isTermsNotAgreed(e),
  );
  assert.equal(termsRequired, 1, "403 TERMS_NOT_AGREED면 동의 화면으로 보내라고 알림");
  global.fetch = problem(403, "FORBIDDEN");
  await assert.rejects(client.api.get("/api/admin/users"), (e) => !client.isTermsNotAgreed(e));
  global.fetch = problem(409, "TERMS_NOT_AGREED");
  await assert.rejects(client.api.get("/api/users/me/favorites"));
  assert.equal(termsRequired, 1, "다른 오류는 알리지 않음");
  stopTerms();

  // 브라우저 푸시의 등록·해제·로그아웃 순서를 합성 구독으로 확인해요. 실제 푸시 서버는 부르지 않아요.
  const push = require("../src/shared/lib/push.ts");
  const navigatorDescriptor = Object.getOwnPropertyDescriptor(globalThis, "navigator");
  let subscription = null;
  const pushEvents = [];
  const fakeSubscription = () => ({
    endpoint: "https://fcm.googleapis.com/synthetic-current-device",
    toJSON: () => ({ endpoint: "https://fcm.googleapis.com/synthetic-current-device", keys: {} }),
    async unsubscribe() {
      pushEvents.push("browser-unsubscribe");
      subscription = null;
      return true;
    },
  });
  Object.defineProperty(globalThis, "navigator", {
    configurable: true,
    value: {
      userAgent: "Synthetic test browser",
      serviceWorker: {
        async getRegistration() {
          return {
            pushManager: {
              async getSubscription() {
                return subscription;
              },
            },
          };
        },
      },
    },
  });
  window.PushManager = function PushManager() {};
  window.Notification = function Notification() {};
  const originalPut = client.api.put;
  const originalDelete = client.api.delete;
  let released;
  let registrationStarted;
  const started = new Promise((resolve) => {
    registrationStarted = resolve;
  });
  const registrationGate = new Promise((resolve) => {
    released = resolve;
  });
  client.api.put = async (url, body) => {
    assert.equal(url, endpoints.pushSubscriptions);
    assert.equal(body.endpoint, "https://fcm.googleapis.com/synthetic-current-device");
    pushEvents.push("server-register");
    registrationStarted();
    await registrationGate;
  };
  client.api.delete = async (url, options) => {
    assert.equal(url, endpoints.pushSubscriptions, "다른 기기 전체 해제 경로를 부르지 않음");
    assert.deepEqual(options.body, {
      endpoint: "https://fcm.googleapis.com/synthetic-current-device",
    });
    pushEvents.push("server-delete");
  };
  subscription = fakeSubscription();
  const registering = push.syncExistingPushSubscription();
  await started;
  let sessionLive = true;
  const loggingOut = push.logoutWithPushCleanup(async () => {
    sessionLive = false;
    pushEvents.push("server-logout");
  });
  const delayedRegister = push.syncExistingPushSubscription(() => sessionLive);
  released();
  assert.equal(await registering, true);
  await loggingOut;
  assert.equal(await delayedRegister, false, "지연된 등록은 로그아웃 뒤 구독을 되살리지 않음");
  assert.deepEqual(pushEvents, [
    "server-register",
    "server-delete",
    "browser-unsubscribe",
    "server-logout",
  ]);
  assert.equal(subscription, null);

  subscription = fakeSubscription();
  pushEvents.length = 0;
  client.api.delete = async () => {
    throw new Error("Synthetic delete failure");
  };
  await assert.rejects(push.logoutWithPushCleanup(async () => pushEvents.push("server-logout")));
  assert.deepEqual(pushEvents, [], "서버 해제 실패는 로그아웃 성공으로 넘기지 않음");
  assert.notEqual(subscription, null);

  client.api.put = async () => {
    throw new Error("Synthetic registration failure");
  };
  await assert.rejects(push.syncExistingPushSubscription());
  assert.equal(subscription, null, "계정 동기화 실패면 이전 회원 알림을 남기지 않음");
  assert.deepEqual(pushEvents, ["browser-unsubscribe"]);
  subscription = fakeSubscription();
  pushEvents.length = 0;
  assert.equal(await push.syncExistingPushSubscription(() => false), false);
  assert.deepEqual(pushEvents, [], "취소된 계정의 구독을 등록하지 않음");
  await push.stopBrowserPushSubscription();
  assert.equal(subscription, null, "비로그인 상태의 이전 브라우저 구독도 해제 가능");
  client.api.put = originalPut;
  client.api.delete = originalDelete;
  if (navigatorDescriptor) Object.defineProperty(globalThis, "navigator", navigatorDescriptor);
  else delete globalThis.navigator;
  delete window.PushManager;
  delete window.Notification;

  // 검수 PDF는 인증 정보를 신뢰하는 원문 경로에만 붙이고 브라우저 캐시를 남기지 않아요.
  const { fetchAdminPdf } = require("../src/features/admin/trace.ts");
  window.location = new URL("https://app.test/admin/review/trace");
  let pdfRequests = 0;
  global.fetch = async (url, init) => {
    pdfRequests++;
    assert.equal(url, "https://app.test/api/admin/reviews/job-1/files/file-1");
    assert.equal(init.cache, "no-store");
    return new Response(new Uint8Array([1, 2, 3]));
  };
  assert.equal((await fetchAdminPdf("/api/admin/reviews/job-1/files/file-1")).byteLength, 3);
  for (const bad of [
    "https://attacker.invalid/api/admin/reviews/job-1/files/file-1",
    "//attacker.invalid/api/admin/reviews/job-1/files/file-1",
    "/api/users/me",
    "/api/admin/reviews/job-1/files/file-1?token=synthetic",
  ])
    await assert.rejects(fetchAdminPdf(bad));
  assert.equal(pdfRequests, 1, "의도한 원문 경로 밖에는 요청하지 않음");
  console.log(
    "UI regression checks passed: unknown inputs, explicit false/zero, legacy conditions, optional birth, money formatting, safe links and return paths, API paths, device data retention and clearing, push/logout sequencing, admin PDF boundary, terms gate, security headers, service worker origin, report links, analytics opt-out.",
  );
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
