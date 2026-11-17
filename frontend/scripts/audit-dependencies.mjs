import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath, pathToFileURL } from "node:url";

const levels = new Set(["moderate", "high", "critical"]);

function advisories(report) {
  if (!report || typeof report.advisories !== "object" || !report.metadata?.vulnerabilities) {
    throw new Error("의존성 감사 응답이 불완전해요");
  }
  const values = Object.values(report.advisories);
  const count = [...levels].reduce((sum, level) => {
    const value = report.metadata.vulnerabilities[level];
    if (!Number.isInteger(value) || value < 0) throw new Error("감사 집계 형식이 잘못됐어요");
    return sum + value;
  }, 0);
  const serious = values.filter((a) => levels.has(a.severity));
  if (count !== serious.length) throw new Error("감사 경보와 집계가 일치하지 않아요");
  return serious;
}

export function evaluateAudits(production, complete, policy, now = new Date()) {
  if (advisories(production).length)
    throw new Error("운영 의존성의 중간 이상 취약점은 예외 없이 차단해요");
  const exceptions = [];
  for (const advisory of advisories(complete)) {
    const issued = Date.parse(policy.issuedAt);
    const expires = Date.parse(policy.expiresAt);
    const active =
      policy.enabled === true &&
      Number.isFinite(issued) &&
      Number.isFinite(expires) &&
      issued <= +now &&
      +now < expires &&
      expires - issued <= 7 * 86400000;
    const exact =
      policy.advisory === "GHSA-fc5q-39xc-vjpf" &&
      policy.package === "picomatch" &&
      policy.pathPrefix === ".>eslint-config-next>" &&
      advisory.github_advisory_id === policy.advisory &&
      advisory.module_name === policy.package;
    const findings = advisory.findings;
    const devOnly =
      Array.isArray(findings) &&
      findings.length > 0 &&
      findings.every(
        (finding) =>
          finding.dev === true &&
          ["2.3.2", "4.0.7"].includes(finding.version) &&
          Array.isArray(policy.versions) &&
          policy.versions.includes(finding.version) &&
          Array.isArray(finding.paths) &&
          finding.paths.length > 0 &&
          finding.paths.every(
            (p) =>
              typeof p === "string" && p.startsWith(policy.pathPrefix) && p.endsWith(">picomatch"),
          ),
      );
    if (!active || !exact || !devOnly)
      throw new Error(`차단된 의존성 경보: ${advisory.github_advisory_id ?? advisory.id}`);
    exceptions.push({
      advisory: policy.advisory,
      severity: advisory.severity,
      expiresAt: policy.expiresAt,
    });
  }
  return {
    productionVulnerabilities: production.metadata.vulnerabilities,
    completeVulnerabilities: complete.metadata.vulnerabilities,
    reportedAdvisories: Object.values(complete.advisories).map((a) => ({
      advisory: a.github_advisory_id ?? a.id,
      package: a.module_name,
      severity: a.severity,
    })),
    exceptions,
  };
}

function audit(production) {
  // Windows 명령은 고정된 pnpm audit 인자만 사용하며 외부 입력을 셸에 넣지 않는다.
  const windows = process.platform === "win32";
  const command = windows ? process.env.ComSpec || "cmd.exe" : "pnpm";
  const args = windows
    ? ["/d", "/s", "/c", production ? "pnpm audit --json --prod" : "pnpm audit --json"]
    : ["audit", "--json", ...(production ? ["--prod"] : [])];
  const result = spawnSync(command, args, {
    cwd: fileURLToPath(new URL("../", import.meta.url)),
    encoding: "utf8",
    timeout: 60000,
    maxBuffer: 5 * 1024 * 1024,
  });
  if (result.error || ![0, 1].includes(result.status))
    throw new Error("의존성 감사 실행에 실패했어요");
  try {
    return JSON.parse(result.stdout);
  } catch {
    throw new Error("감사 응답을 읽지 못했어요");
  }
}

export function main() {
  const policy = JSON.parse(readFileSync(new URL("./audit-policy.json", import.meta.url), "utf8"));
  const result = evaluateAudits(audit(true), audit(false), policy);
  console.log(JSON.stringify(result));
  for (const exception of result.exceptions) {
    console.warn(
      `개발 의존성 고위험 경보 유지: ${exception.advisory} / 한시 승인 만료 ${exception.expiresAt}`,
    );
  }
}

if (process.argv[1] && pathToFileURL(process.argv[1]).href === import.meta.url) {
  try {
    main();
  } catch (error) {
    console.error(error.message);
    process.exitCode = 1;
  }
}
