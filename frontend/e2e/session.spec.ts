import { expect, test } from "@playwright/test";
import { apiOrigin, reset, session, bearer } from "./support";

test("인증·refresh 회전·계정 분리·타인 수정 방지", async ({ page, request }) => {
  const fixture = await reset(request);
  expect((await request.get(`${apiOrigin}/api/users/me/preparations`)).status()).toBe(401);
  await session(page, "u1");
  const before = (await page.context().cookies()).find((c) => c.name === "refresh_token")!.value;
  const auth = await bearer(page);
  expect((await page.context().cookies()).find((c) => c.name === "refresh_token")!.value).not.toBe(
    before,
  );
  const created = await page.request.put(
    `${apiOrigin}/api/users/me/preparations/notices/${fixture.noticeId}`,
    { headers: auth },
  );
  expect(created.status()).toBe(201);
  const p = await created.json();
  await page.goto(`/me/preparations/${p.id}`);
  await expect(
    page.getByRole("heading", { name: "E2E 청년 주거 신청 공고", exact: true }),
  ).toBeVisible();
  await page.goto("/me");
  // 로그아웃 응답의 쿠키 삭제가 다음 테스트 계정의 쿠키를 지우지 않도록 완료 후 이동을 기다려요.
  await Promise.all([
    page.waitForURL("/"),
    page.getByRole("button", { name: "로그아웃", exact: true }).click(),
  ]);
  await session(page, "u2");
  const secondAuth = await bearer(page);
  expect(
    (
      await page.request.patch(`${apiOrigin}/api/users/me/preparations/${p.id}`, {
        headers: secondAuth,
        data: { status: "SUBMITTED", expectedRevision: 0 },
      })
    ).status(),
  ).toBe(404);
  await page.goto(`/me/preparations/${p.id}`);
  await expect(
    page.getByRole("heading", { name: "E2E 청년 주거 신청 공고", exact: true }),
  ).toHaveCount(0);
  await page.goto("/me/preparations");
  await expect(page.getByText("아직 준비 중인 공고가 없어요.", { exact: true })).toBeVisible();
  await page.context().addCookies([
    {
      name: "refresh_token",
      value: "expired-e2e-token",
      domain: "127.0.0.1",
      path: "/api/auth",
      httpOnly: true,
      secure: false,
      sameSite: "Lax",
    },
  ]);
  await page.reload();
  await expect(page.getByRole("link", { name: "로그인하고 신청 준비함 사용하기" })).toBeVisible();
});
