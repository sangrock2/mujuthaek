/* eslint-disable @typescript-eslint/no-require-imports -- focused TypeScript/SSR regression runner */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const Module = require("node:module");
const { test } = require("node:test");
const ts = require("typescript");
const React = require("react");
const { renderToStaticMarkup } = require("react-dom/server");
const root = path.resolve(__dirname, "../src");
const resolve = Module._resolveFilename;
Module._resolveFilename = function (name, parent, ...args) {
  return resolve.call(
    this,
    name.startsWith("@/") ? path.join(root, name.slice(2)) : name,
    parent,
    ...args,
  );
};
for (const ext of [".ts", ".tsx"]) {
  require.extensions[ext] = (module, filename) => {
    const { outputText } = ts.transpileModule(fs.readFileSync(filename, "utf8"), {
      fileName: filename,
      compilerOptions: {
        target: ts.ScriptTarget.ES2017,
        module: ts.ModuleKind.CommonJS,
        jsx: ts.JsxEmit.ReactJSX,
        esModuleInterop: true,
      },
    });
    module._compile(outputText, filename);
  };
}
let snapshot = { status: "ready", device: null, session: null };
let criteria;
const load = Module._load;
Module._load = function (name, parent, ...args) {
  if (name === "next/navigation") return { usePathname: () => "/notices/public-notice" };
  const filename = Module._resolveFilename(name, parent);
  if (filename === path.join(root, "features/conditions/store.ts"))
    return { useConditions: () => snapshot };
  if (filename === path.join(root, "features/eligibility/criteria.ts"))
    return { useCriteria: () => ({ data: criteria }) };
  return load.call(this, name, parent, ...args);
};
const {
  PersonalizationSummary,
} = require("../src/features/conditions/components/PersonalizationSummary.tsx");
const { BenefitEmptyState } = require("../src/features/benefits/components/BenefitEmptyState.tsx");
const { CheckAction } = require("../src/shared/ui/CheckAction.tsx");
const { EligibilityCard } = require("../src/features/notice/components/EligibilityCard.tsx");
const { DocumentChecklist } = require("../src/features/notice/components/DocumentChecklist.tsx");
const { documentsBySubmission } = require("../src/features/notice/documents.ts");
const { inputHrefOf, profileStepOf } = require("../src/features/conditions/needs.ts");
const { defaultDevice } = require("../src/features/profile/defaults.ts");
const { toListing } = require("../src/features/homes/search.ts");
const { statusLabel } = require("../src/features/notice/format.ts");
const { toVersions } = require("../src/features/notice/versions.ts");
const { trust } = require("../src/features/main/landing.ts");
const render = (component, props) => renderToStaticMarkup(React.createElement(component, props));
const summary = (props = {}) =>
  render(PersonalizationSummary, {
    kind: "homes",
    loading: false,
    error: false,
    eligible: 0,
    needsInput: 10,
    ...props,
  });
const blank = () => defaultDevice({ defaultPriorities: [] });

test("anonymous and saved-but-empty conditions never imply ineligibility", () => {
  snapshot = { status: "ready", device: null, session: null };
  assert.match(summary(), /조건을 입력하면/);
  assert.doesNotMatch(summary(), /0곳/);
  snapshot.device = blank();
  assert.match(summary(), /조건을 입력하면/);
  snapshot.device.head = "member";
  assert.match(summary(), /지원 가능/); // false인 householdHead도 실제 입력
  assert.match(summary(), /0곳/);
});
test("financial-only conditions are recognized with the actual criteria conversion", () => {
  snapshot = {
    status: "ready",
    device: blank(),
    session: { income: "", asset: "1000", assetUnknown: false, available: "", rankChecks: [] },
  };
  criteria = { assetCutsWon: [100_000_000], carCutsWon: [] };
  assert.match(summary(), /지원 가능/);
  criteria = undefined;
});
test("loading and request failures do not turn into zero eligible counts", () => {
  assert.match(summary({ loading: true }), /확인하고 있어요/);
  assert.doesNotMatch(summary({ loading: true }), /0곳/);
  assert.match(summary({ error: true }), /다시 시도/);
  assert.doesNotMatch(summary({ error: true }), /0곳/);
});
test("empty benefits give an anonymous user a returnable input route and a browse option", () => {
  snapshot = { status: "ready", device: null, session: null };
  const html = render(BenefitEmptyState, { filtered: false, onReset() {} });
  assert.match(html, /아직 조건을 입력하지 않았어요/);
  assert.match(html, /href="\/profile\?next=%2Fbenefits"/);
  assert.match(html, /href="\/homes"/);
  assert.doesNotMatch(html, /지금 받을 수 있는 혜택이 없어요/);
});
test("a category with no results offers reset without claiming every benefit is unavailable", () => {
  snapshot = { status: "ready", device: { ...blank(), head: "head" }, session: null };
  const html = render(BenefitEmptyState, { filtered: true, onReset() {} });
  assert.match(html, /전체 분야 보기/);
  assert.match(html, /모든 혜택의 신청 자격이 없다는 뜻은 아니에요/);
});
test("needs link to existing input steps; non-input requirements remain source checks", () => {
  assert.equal(inputHrefOf(["applicant.income"]), "/profile?step=2");
  assert.equal(inputHrefOf(["assets"]), "/profile?step=2");
  assert.equal(inputHrefOf(["applicant.marital"]), "/profile?step=2");
  assert.equal(inputHrefOf(["householdSize"]), "/profile?step=2");
  assert.equal(inputHrefOf(["homeOwner"]), "/profile?step=3");
  assert.equal(inputHrefOf(["subscription.months"]), "/profile?step=3");
  assert.equal(inputHrefOf(["welfareStatuses"]), "/profile?step=2");
  assert.equal(inputHrefOf(["birthDate"]), "/profile?step=1");
  assert.equal(inputHrefOf(["business.history"]), "/business/onboarding");
  assert.equal(inputHrefOf(["unavailable.input"]), undefined);
  for (const value of [null, "0", "4", "-1", "3<script>"]) assert.equal(profileStepOf(value), 1);
  assert.equal(profileStepOf("3"), 3);
});
test("input action returns to the public notice without copying URL queries or financial data", () => {
  const html = render(CheckAction, { inputHref: "/profile?step=3", web: true });
  assert.match(html, /\/profile\?step=3&amp;next=%2Fnotices%2Fpublic-notice/);
  const review = render(CheckAction, { web: true, onReview() {} });
  assert.match(review, /<button/);
  assert.match(review, /원문 확인/);
});
test("all-unknown eligibility is expanded and separates input repair from source review", () => {
  const html = render(EligibilityCard, {
    loading: false,
    error: false,
    variant: "web",
    onOpenOriginal() {},
    judgment: {
      verdict: "check",
      targets: [
        {
          id: "t",
          name: "일반",
          verdict: "check",
          counts: { met: 0, notMet: 0, unknown: 2 },
          items: [
            { id: "income", label: "소득", status: "unknown", inputHref: "/profile?step=3" },
            { id: "review", label: "원문 검수", status: "unknown", reason: "확인 중", page: 2 },
          ],
        },
      ],
    },
  });
  assert.match(html, /<details[^>]* open=""/);
  assert.match(html, /1개는 조건 입력으로/);
  assert.match(html, /개인정보를 더 입력해도 해결되지 않을 수/);
  assert.match(html, /원문 검수/);
});
test("documents keep conditional recipients and separate application from contract submission", () => {
  const items = [
    { id: "a", name: "등본", appliesTo: "신청자 전원", submissionTime: "신청 접수 시", desc: "" },
    {
      id: "b",
      name: "사업자등록증",
      appliesTo: "사업자인 경우",
      submissionTime: "신청 접수 시",
      desc: "",
    },
    {
      id: "c",
      name: "계약 도장",
      appliesTo: "현장 계약자",
      submissionTime: "현장 계약 시",
      desc: "",
    },
    { id: "d", name: "별도 서류", when: "해당자", desc: "" },
  ];
  assert.deepEqual(
    documentsBySubmission(items).map(([stage, docs]) => [stage, docs.length]),
    [
      ["신청 접수 시", 2],
      ["현장 계약 시", 1],
      ["제출 시점은 원문 확인", 1],
    ],
  );
  const html = render(DocumentChecklist, { items });
  assert.match(html, /제출 대상 · 사업자인 경우/);
  assert.match(html, /제출 시점 · 현장 계약 시/);
  assert.doesNotMatch(html, /모두 내요/);
});
test("listing fallback does not claim that an original with per-unit prices has no prices", () => {
  const item = {
    id: "id",
    title: "공고",
    provider: "SH",
    noticeType: null,
    regionCode: null,
    regionName: null,
    status: "UPCOMING",
    applyStart: "2026-11-16",
    applyEnd: "2026-11-19",
    dday: 2,
    overall: "NEEDS_INPUT",
    prepareCostWon: null,
    prepareCostNote: "PRICE_NOT_ANNOUNCED",
    areaScore: null,
    tags: [],
    siteCount: 1,
  };
  assert.match(toListing(item).prepNote, /상세에서 확인/);
  assert.doesNotMatch(toListing(item).prepNote, /공고에 금액이.*없/);
  assert.equal(toListing(item).due, statusLabel.UPCOMING);
  assert.equal(toListing({ ...item, status: "CLOSED", dday: -1 }).due, "접수 마감");
});
test("privacy explanation distinguishes temporary housing storage and exact-value loan transmission", () => {
  const text = trust[0].desc;
  assert.match(text, /탭에 임시 보관/);
  assert.match(text, /구간/);
  assert.match(text, /대출.*정확한 금액.*서버로 보내/);
  assert.doesNotMatch(text, /어디에도 저장하지 않/);
});

test("service receipt dates remain visible for one version and unchanged latest versions", () => {
  const first = {
    version: 1,
    kind: "NOTICE",
    reviewStatus: "APPROVED",
    changedFields: [],
    receivedAt: "2026-11-10T12:00:00",
  };
  assert.equal(toVersions([first]).length, 1);
  assert.equal(toVersions([first])[0].label, "서비스 첫 반영");
  assert.match(toVersions([first])[0].day, /2026년/);
  const rows = toVersions([
    first,
    { ...first, version: 2, receivedAt: "2026-11-11T12:00:00" },
    { ...first, version: 3, receivedAt: "2026-11-12T12:00:00" },
  ]);
  assert.deepEqual(
    rows.map((x) => x.version),
    [1, 3],
  );
  assert.match(rows[1].day, /11월 12일/);
  assert.equal(rows[1].label, "정보 다시 반영");
});
