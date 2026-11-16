import assert from "node:assert/strict";
import { test } from "node:test";
import { isolatedEnvironment, localDockerEndpoint } from "./e2e-environment.mjs";

test("provider secrets and production URLs never enter E2E child processes", () => {
  const input = Object.fromEntries(
    [
      "OPENAI_API_KEY",
      "GOOGLE_CLIENT_SECRET",
      "KAKAO_CLIENT_SECRET",
      "AWS_ACCESS_KEY_ID",
      "GITHUB_TOKEN",
      "GH_TOKEN",
      "VERCEL_TOKEN",
      "VERCEL",
      "CANONICAL_WEB_ORIGIN",
      "NODE_OPTIONS",
      "JAVA_TOOL_OPTIONS",
      "DOCKER_HOST",
      "DOCKER_CONTEXT",
      "SLACK_WEBHOOK_URL",
      "DATABASE_URL",
      "NEXT_PUBLIC_PRODUCTION_SETTING",
    ].map((key) => [key, "synthetic-production-value"]),
  );
  const output = isolatedEnvironment(
    { ...input, Path: "local-path", JAVA_HOME: "local-jdk" },
    false,
    "synthetic-key",
  );
  for (const key of Object.keys(input)) assert.equal(output[key], undefined, key);
  assert.equal(output.Path, "local-path");
  assert.equal(output.JAVA_HOME, "local-jdk");
  assert.equal(output.API_ORIGIN, "http://127.0.0.1:18080");
  assert.equal(output.E2E_CONTROL_KEY, "synthetic-key");
  assert.equal(output.AWS_EC2_METADATA_DISABLED, "true");
});

test("only local daemon transports are accepted", () => {
  assert.equal(localDockerEndpoint("unix:///var/run/docker.sock"), true);
  assert.equal(localDockerEndpoint("npipe:////./pipe/dockerDesktopLinuxEngine"), true);
  for (const value of ["ssh://production", "tcp://production:2376", "https://remote", "", null])
    assert.equal(localDockerEndpoint(value), false);
});
