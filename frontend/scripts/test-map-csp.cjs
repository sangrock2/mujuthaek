/* eslint-disable @typescript-eslint/no-require-imports -- focused TypeScript policy regression */
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const Module = require("node:module");
const ts = require("typescript");
const { test } = require("node:test");
const file = path.resolve(__dirname, "../src/shared/lib/securityHeaders.ts");
const compiled = ts.transpileModule(fs.readFileSync(file, "utf8"), {
  compilerOptions: { target: ts.ScriptTarget.ES2017, module: ts.ModuleKind.CommonJS },
}).outputText;
const policyModule = new Module(file, module);
policyModule.filename = file;
policyModule._compile(compiled, file);
const { contentSecurityPolicy } = policyModule.exports;
const policy = (enabled) =>
  Object.fromEntries(
    contentSecurityPolicy({ dev: false, apiOrigin: "", analytics: false, kakaoMap: enabled })
      .split(";")
      .map((d) => d.trim().split(/\s+/))
      .filter((d) => d[0])
      .map(([name, ...hosts]) => [name, hosts]),
  );

test("enabled map permits the SDK and its observed nested Kakao script host", () => {
  const p = policy(true);
  for (const host of ["dapi.kakao.com", "t1.kakaocdn.net"])
    assert.ok(new Set(p["script-src"]).has(host));
});
test("enabled map permits the actual tile and UI image hosts", () => {
  const p = policy(true);
  for (const host of ["t1.kakaocdn.net", "mts.kakaocdn.net"])
    assert.ok(new Set(p["img-src"]).has(host));
});
test("tile permission does not grant script execution or arbitrary outbound connections", () => {
  const p = policy(true);
  assert.ok(!new Set(p["script-src"]).has("mts.kakaocdn.net"));
  assert.deepEqual(p["connect-src"], ["'self'", "dapi.kakao.com"]);
  assert.deepEqual(
    new Set(p["script-src"]),
    new Set(["'self'", "'unsafe-inline'", "dapi.kakao.com", "t1.daumcdn.net", "t1.kakaocdn.net"]),
  );
  assert.ok(!new Set(p["img-src"]).has("*.kakaocdn.net"));
});
test("disabled map grants no Kakao or Daum CDN permission", () => {
  for (const sources of Object.values(policy(false)))
    for (const source of sources) assert.doesNotMatch(source, /kakao|daum/);
});
