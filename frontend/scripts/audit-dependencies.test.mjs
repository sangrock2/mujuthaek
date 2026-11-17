import assert from "node:assert/strict";
import test from "node:test";
import { evaluateAudits } from "./audit-dependencies.mjs";

const now = new Date("2026-11-18T00:00:00Z");
const policy = {
  enabled: true,
  advisory: "GHSA-fc5q-39xc-vjpf",
  package: "picomatch",
  versions: ["2.3.2", "4.0.7"],
  pathPrefix: ".>eslint-config-next>",
  issuedAt: "2026-11-18T00:00:00+09:00",
  expiresAt: "2026-11-25T00:00:00+09:00",
};
const item = {
  github_advisory_id: policy.advisory,
  module_name: "picomatch",
  severity: "high",
  findings: [{ dev: true, version: "4.0.7", paths: [".>eslint-config-next>tinyglobby>picomatch"] }],
};
const report = (items = []) => ({
  advisories: Object.fromEntries(items.map((x, i) => [i, x])),
  metadata: { vulnerabilities: { moderate: 0, high: items.length, critical: 0 } },
});
const check = (advisory = item, accepted = policy) =>
  evaluateAudits(report(), report([advisory]), accepted, now);

test("zero vulnerabilities passes without an exception", () =>
  assert.deepEqual(evaluateAudits(report(), report(), {}, now).exceptions, []));
test("only the approved dev-only finding is accepted and remains visible", () =>
  assert.equal(check().exceptions[0].advisory, policy.advisory));
test("unapproved policy fails closed", () =>
  assert.throws(() => check(item, { ...policy, enabled: false })));
test("production findings never use the exception", () =>
  assert.throws(() => evaluateAudits(report([item]), report([item]), policy, now)));
test("expired and overlong windows fail closed", () => {
  assert.throws(() => check(item, { ...policy, expiresAt: "2026-11-17T00:00:00Z" }));
  assert.throws(() => check(item, { ...policy, expiresAt: "2026-12-18T00:00:00Z" }));
});
test("a new advisory is blocked", () =>
  assert.throws(() => check({ ...item, github_advisory_id: "GHSA-new-new-new" })));
test("runtime or unrelated paths are blocked despite the dev flag", () =>
  assert.throws(() =>
    check({ ...item, findings: [{ ...item.findings[0], paths: [".>next>picomatch"] }] }),
  ));
test("missing dev proof and changed versions are blocked", () => {
  assert.throws(() => check({ ...item, findings: [{ ...item.findings[0], dev: false }] }));
  assert.throws(() => check({ ...item, findings: [{ ...item.findings[0], version: "4.0.6" }] }));
});
test("an incomplete scanner response or hidden finding blocks", () => {
  assert.throws(() => evaluateAudits({}, report(), policy, now));
  assert.throws(() =>
    evaluateAudits(
      { ...report(), metadata: { vulnerabilities: { moderate: 0, high: 1, critical: 0 } } },
      report(),
      policy,
      now,
    ),
  );
});
