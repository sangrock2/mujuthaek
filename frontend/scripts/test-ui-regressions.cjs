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
      compilerOptions: {
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
const { secureApiOrigin } = require("../src/shared/lib/api/origin.ts");
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
console.log(
  "UI regression checks passed: unknown inputs, explicit false/zero, legacy conditions, optional birth, money formatting.",
);
