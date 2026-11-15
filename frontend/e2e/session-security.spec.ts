import { expect, test } from "@playwright/test";
import { apiOrigin, reset, session, bearer } from "./support";

test("두 탭의 재발급을 조정하고 로그아웃 시 다른 탭의 개인 캐시도 비운다", async ({
  page,
  request,
}) => {
  await reset(request);
  await session(page, "u1");
  const auth = await bearer(page);
  const other = await page.context().newPage();
  await Promise.all([page.goto("/me"), other.goto("/me")]);
  await expect(page.getByRole("button", { name: "로그아웃", exact: true })).toBeVisible();
  await expect(other.getByRole("button", { name: "로그아웃", exact: true })).toBeVisible();
  const cookie = (await page.context().cookies()).find((item) => item.name === "refresh_token")!;
  await page.getByRole("button", { name: "로그아웃", exact: true }).click();
  await expect(page).toHaveURL("/");
  await expect(other.getByRole("button", { name: "로그아웃", exact: true })).toHaveCount(0);
  expect((await request.get(`${apiOrigin}/api/users/me`, { headers: auth })).status()).toBe(401);
  expect(
    (
      await request.post(`${apiOrigin}/api/auth/refresh`, {
        headers: { Cookie: `refresh_token=${cookie.value}` },
      })
    ).status(),
  ).toBe(401);
  await other.close();
});

test("로그아웃 통신 실패를 성공처럼 표시하거나 개인 캐시를 지우지 않는다", async ({
  page,
  request,
}) => {
  await reset(request);
  await session(page, "u1");
  await page.goto("/me");
  const button = page.getByRole("button", { name: "로그아웃", exact: true });
  await expect(button).toBeVisible();
  await page.route("**/api/auth/logout", (route) =>
    route.fulfill({
      status: 503,
      contentType: "application/problem+json",
      body: JSON.stringify({ status: 503 }),
    }),
  );
  await button.click();
  await expect(
    page.getByRole("alert").filter({ hasText: "로그아웃을 완료하지 못했어요" }),
  ).toBeVisible();
  await expect(button).toBeVisible();
  await expect(page).toHaveURL(/\/me$/);
  await page.unroute("**/api/auth/logout");
  await button.click();
  await expect(page).toHaveURL("/");
});
