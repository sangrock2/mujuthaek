import { expect, type APIRequestContext, type Page } from "@playwright/test";
export const apiOrigin = "http://127.0.0.1:18080";
export const notificationOrigin = "http://127.0.0.1:18081";
export function controlHeaders() {
  if (!process.env.E2E_CONTROL_KEY)
    throw new Error("Run pnpm test:e2e to create an isolated environment");
  return { "X-E2E-Key": process.env.E2E_CONTROL_KEY };
}
export async function control(request: APIRequestContext, action: string) {
  const response = await request.post(`${apiOrigin}/_e2e/${action}`, { headers: controlHeaders() });
  expect(response.ok(), `${action}: ${await response.text()}`).toBeTruthy();
  return response;
}
export async function reset(request: APIRequestContext) {
  return (await control(request, "reset")).json() as Promise<{
    noticeId: string;
    user1: string;
    user2: string;
  }>;
}
export async function session(page: Page, account: "u1" | "u2") {
  await control(page.context().request, `session/${account}`);
}
export async function bearer(page: Page) {
  const response = await page.context().request.post(`${apiOrigin}/api/auth/refresh`, {
    headers: { Origin: "http://127.0.0.1:13000" },
  });
  expect(response.ok()).toBeTruthy();
  return { Authorization: `Bearer ${(await response.json()).accessToken}` };
}
