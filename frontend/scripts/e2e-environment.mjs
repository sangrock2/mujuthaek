// Only tools and OS paths cross into disposable E2E processes, never ambient provider credentials.
const INHERITED = new Set([
  "PATH",
  "PATHEXT",
  "SYSTEMROOT",
  "WINDIR",
  "COMSPEC",
  "HOME",
  "USERPROFILE",
  "APPDATA",
  "LOCALAPPDATA",
  "PROGRAMDATA",
  "PROGRAMFILES",
  "PROGRAMFILES(X86)",
  "PROGRAMW6432",
  "TEMP",
  "TMP",
  "TMPDIR",
  "JAVA_HOME",
  "GRADLE_USER_HOME",
  "PNPM_HOME",
  "COREPACK_HOME",
  "LANG",
  "LC_ALL",
  "TZ",
  "TERM",
  "COLORTERM",
  "CI",
  "GITHUB_ACTIONS",
  "DISPLAY",
  "WAYLAND_DISPLAY",
  "XAUTHORITY",
  "XDG_RUNTIME_DIR",
]);

export function isolatedEnvironment(inherited, preview, controlKey) {
  return {
    ...Object.fromEntries(
      Object.entries(inherited).filter(([key]) => INHERITED.has(key.toUpperCase())),
    ),
    E2E_ALLOW_LOCAL: "1",
    E2E_CONTROL_KEY: controlKey,
    NEXT_TELEMETRY_DISABLED: "1",
    AWS_EC2_METADATA_DISABLED: "true",
    NEXT_PUBLIC_USE_MOCKS: "false",
    NEXT_PUBLIC_API_PREVIEW: preview ? "true" : "false",
    NEXT_PUBLIC_API_BASE_URL: "",
    NEXT_PUBLIC_GA_ID: "",
    NEXT_PUBLIC_KAKAO_MAP_KEY: "",
    NEXT_PUBLIC_VAPID_PUBLIC_KEY: "",
    TRAFFIC_INGEST_URL: "",
    TRAFFIC_INGEST_TOKEN: "",
    API_ORIGIN: "http://127.0.0.1:18080",
  };
}

export function localDockerEndpoint(endpoint) {
  return (
    typeof endpoint === "string" &&
    (endpoint.startsWith("unix:///") || endpoint.startsWith("npipe:////./pipe/"))
  );
}
