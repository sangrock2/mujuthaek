import { spawn, spawnSync } from "node:child_process";
import { mkdirSync, openSync, closeSync, writeFileSync, readFileSync } from "node:fs";
import { createServer } from "node:http";
import { randomBytes } from "node:crypto";
import { fileURLToPath } from "node:url";
import path from "node:path";
import net from "node:net";
import { isolatedEnvironment, localDockerEndpoint } from "./e2e-environment.mjs";

const frontend = fileURLToPath(new URL("../", import.meta.url));
const resumePreview = process.argv.includes("--resume-preview");
const previewMode = process.argv.includes("--preview") || resumePreview;
const previousPreview = resumePreview
  ? JSON.parse(readFileSync(path.join(frontend, "test-results/servers/preview.json"), "utf8"))
  : null;
const root = path.resolve(frontend, "..");
const project =
  process.env.E2E_PROJECT ?? previousPreview?.project ?? `mujuthaek-e2e-${process.pid}`;
if (!/^mujuthaek-e2e-[a-z0-9-]+$/.test(project)) throw new Error("Invalid E2E_PROJECT");
const compose = ["compose", "-p", project, "-f", path.join(root, "backend/infra/e2e/compose.yml")];
const logs = path.join(frontend, "test-results/servers");
mkdirSync(logs, { recursive: true });
const env = isolatedEnvironment(process.env, previewMode, randomBytes(32).toString("hex"));
const children = [],
  handles = [];
let cleaned = false,
  composeStarted = false;
function command(executable, args, cwd = frontend, log) {
  const child = spawn(executable, args, {
    cwd,
    env,
    stdio: log ? ["ignore", log, log] : "inherit",
    windowsHide: true,
    shell: false,
    detached: process.platform !== "win32",
  });
  children.push(child);
  child.on("error", (error) => console.error(error.message));
  return child;
}
function wait(child) {
  return new Promise((resolve, reject) => {
    child.once("error", reject);
    child.once("exit", (code, signal) =>
      code === 0
        ? resolve()
        : reject(new Error(`Process failed (${signal ?? code}); see test-results/servers`)),
    );
  });
}
function gradle(service) {
  const fd = openSync(path.join(logs, `${service}.log`), "w");
  handles.push(fd);
  const cwd = path.join(root, "backend/services", service);
  return process.platform === "win32"
    ? command("cmd.exe", ["/d", "/s", "/c", "gradlew.bat --no-daemon e2eRun"], cwd, fd)
    : command("bash", ["./gradlew", "--no-daemon", "e2eRun"], cwd, fd);
}
async function ready(url, child) {
  const deadline = Date.now() + 180_000;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) throw new Error(`Server exited before readiness: ${url}`);
    try {
      if ((await fetch(url, { signal: AbortSignal.timeout(2000) })).ok) return;
    } catch {
      /* starting */
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`Server readiness timed out: ${url}`);
}
async function preview() {
  const headers = { "X-E2E-Key": env.E2E_CONTROL_KEY };
  let noticeId;
  if (!resumePreview) {
    const seeded = await fetch("http://127.0.0.1:18080/_e2e/reset", { method: "POST", headers });
    if (!seeded.ok) throw new Error(`Preview fixture failed (${seeded.status})`);
    ({ noticeId } = await seeded.json());
  }
  const login = async () => {
    const response = await fetch("http://127.0.0.1:18080/_e2e/session/u1", {
      method: "POST",
      headers,
    });
    if (!response.ok) throw new Error(`Preview login failed (${response.status})`);
    const cookie = response.headers.get("set-cookie");
    if (!cookie) throw new Error("Preview refresh cookie missing");
    return cookie;
  };
  const cookie = await login();
  const refresh = await fetch("http://127.0.0.1:18080/api/auth/refresh", {
    method: "POST",
    headers: { Cookie: cookie.split(";")[0], Origin: "http://127.0.0.1:13000" },
  });
  if (!refresh.ok) throw new Error(`Preview refresh failed (${refresh.status})`);
  const { accessToken } = await refresh.json();
  const previousId = previousPreview?.preparationUrl?.split("/").at(-1);
  if (resumePreview && !/^[a-f0-9-]{36}$/.test(previousId ?? ""))
    throw new Error("Invalid previous preparation ID");
  const created = await fetch(
    resumePreview
      ? `http://127.0.0.1:18080/api/users/me/preparations/${previousId}`
      : `http://127.0.0.1:18080/api/users/me/preparations/notices/${noticeId}`,
    { method: resumePreview ? "GET" : "PUT", headers: { Authorization: `Bearer ${accessToken}` } },
  );
  if (!created.ok) throw new Error(`Preview preparation failed (${created.status})`);
  const preparation = await created.json();
  if (!/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/.test(preparation.id ?? ""))
    throw new Error("Invalid preparation ID");
  const token = resumePreview
    ? new URL(previousPreview.url).pathname.slice(1)
    : randomBytes(24).toString("hex");
  if (!/^[a-f0-9]{48}$/.test(token)) throw new Error("Invalid preview entry token");
  const url = `http://127.0.0.1:13001/${token}`;
  const server = createServer(async (request, response) => {
    if (request.url === `/${token}` && request.method === "GET") {
      try {
        response.writeHead(302, {
          "Set-Cookie": await login(),
          Location: `http://127.0.0.1:13000/me/preparations/${preparation.id}`,
          "Cache-Control": "no-store",
          "Referrer-Policy": "no-referrer",
        });
        response.end();
      } catch (error) {
        response.writeHead(503, { "Content-Type": "text/plain; charset=utf-8" });
        response.end(error.message);
      }
    } else if (request.url === `/${token}/stop` && request.method === "POST") {
      response.writeHead(200);
      response.end("Stopped");
      server.close();
      setImmediate(() => process.emit("SIGTERM"));
    } else {
      response.writeHead(404);
      response.end();
    }
  });
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(13001, "127.0.0.1", resolve);
  });
  writeFileSync(
    path.join(logs, "preview.json"),
    JSON.stringify(
      {
        pid: process.pid,
        project,
        url,
        stopUrl: `${url}/stop`,
        preparationUrl: `http://127.0.0.1:13000/me/preparations/${preparation.id}`,
      },
      null,
      2,
    ),
  );
  console.log(`PREVIEW_URL=${url}`);
  await new Promise(() => {});
}
function cleanup() {
  if (cleaned) return;
  cleaned = true;
  for (const child of children.toReversed()) {
    if (child.exitCode !== null || !child.pid) continue;
    if (process.platform === "win32")
      spawnSync("taskkill", ["/pid", String(child.pid), "/t", "/f"], {
        windowsHide: true,
        stdio: "ignore",
      });
    else {
      try {
        process.kill(-child.pid, "SIGTERM");
      } catch {
        /* stopped */
      }
    }
  }
  for (const fd of handles) closeSync(fd);
  if (composeStarted) {
    const result = spawnSync(
      "docker",
      [...compose, ...(previewMode ? ["stop"] : ["down", "--volumes", "--remove-orphans"])],
      {
        cwd: root,
        env,
        stdio: "inherit",
        windowsHide: true,
        timeout: 60_000,
      },
    );
    if (result.status !== 0) console.error(`Cleanup failed for ${project}`);
  }
}
for (const signal of ["SIGINT", "SIGTERM"])
  process.once(signal, () => {
    cleanup();
    process.exit(1);
  });
try {
  const context = spawnSync(
    "docker",
    ["context", "inspect", "--format", "{{json .Endpoints.docker.Host}}"],
    {
      env,
      encoding: "utf8",
      windowsHide: true,
      timeout: 15_000,
    },
  );
  if (context.status !== 0 || !localDockerEndpoint(JSON.parse(context.stdout.trim())))
    throw new Error("E2E requires a local Docker daemon; remote contexts are refused");
  // 기존 포트의 서버를 재사용하지 않아 공유/운영 서버에 fixture가 적용되는 것을 막는다.
  for (const port of [13000, 18080, 18081, ...(previewMode ? [13001] : [])])
    await new Promise((resolve, reject) => {
      const server = net.createServer();
      server.once("error", () => reject(new Error(`Port ${port} is already in use`)));
      server.listen(port, "127.0.0.1", () => server.close(resolve));
    });
  composeStarted = true;
  await wait(command("docker", [...compose, "up", "-d", "--wait", "--wait-timeout", "120"], root));
  const notification = gradle("notification"),
    api = gradle("api");
  await Promise.all([
    ready("http://127.0.0.1:18080/actuator/health", api),
    ready("http://127.0.0.1:18081/actuator/health", notification),
  ]);
  await wait(
    command(process.execPath, [path.join(frontend, "node_modules/next/dist/bin/next"), "build"]),
  );
  const fd = openSync(path.join(logs, "frontend.log"), "w");
  handles.push(fd);
  const web = command(
    process.execPath,
    [
      path.join(frontend, "node_modules/next/dist/bin/next"),
      "start",
      "--hostname",
      "127.0.0.1",
      "--port",
      "13000",
    ],
    frontend,
    fd,
  );
  await ready("http://127.0.0.1:13000/", web);
  if (previewMode) await preview();
  else
    await wait(
      command(process.execPath, [
        path.join(frontend, "node_modules/@playwright/test/cli.js"),
        "test",
        ...process.argv.slice(2),
      ]),
    );
} catch (error) {
  if (composeStarted) {
    const diagnostic = openSync(path.join(logs, "rabbitmq-startup.log"), "w");
    try {
      spawnSync("docker", [...compose, "logs", "--no-color", "--tail", "160", "rabbitmq"], {
        cwd: root,
        env,
        windowsHide: true,
        timeout: 15_000,
        stdio: ["ignore", diagnostic, diagnostic],
      });
    } finally {
      closeSync(diagnostic);
    }
  }
  console.error(error.message);
  process.exitCode = 1;
} finally {
  cleanup();
}
