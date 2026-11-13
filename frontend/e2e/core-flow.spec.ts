import { expect, test } from "@playwright/test";
import {
  apiOrigin,
  notificationOrigin,
  controlHeaders,
  reset,
  session,
  bearer,
  control,
} from "./support";

test("실제 API로 조건·판정·PDF·준비함·알림·정정을 연결한다", async ({ page, request }) => {
  const fixture = await reset(request);
  await page.clock.setFixedTime(new Date("2026-11-12T02:05:00Z"));
  await page.goto("/profile?next=/homes");
  await page.getByLabel("태어난 해 (숫자)", { exact: true }).fill("1997");
  await page.getByLabel("태어난 달 (숫자)", { exact: true }).fill("03");
  await page.getByLabel("태어난 날 (숫자)", { exact: true }).fill("15");
  for (let i = 0; i < 2; i++) await page.getByRole("button", { name: "다음", exact: true }).click();
  const search = page.waitForResponse(
    (r) => r.url().includes("/api/v1/notices/search") && r.request().method() === "POST",
  );
  await page.getByRole("button", { name: "확인하기", exact: true }).click();
  const searchResponse = await search;
  expect(searchResponse.ok()).toBeTruthy();
  const applicant = searchResponse.request().postDataJSON().applicant;
  expect(applicant.birthDate).toBe("1997-03-15");
  expect(applicant).not.toHaveProperty("children");
  expect(applicant).not.toHaveProperty("householdHead");
  await expect(page.getByText("E2E 청년 주거 신청 공고", { exact: true }).first()).toBeVisible();
  // 응답에서 기대값을 만들지 않고 고정 fixture의 세 결과를 독립적으로 확인한다.
  for (const [applicant, overall] of [
    [{}, "NEEDS_INPUT"],
    [{ birthDate: "1997-03-15" }, "ELIGIBLE"],
    [{ birthDate: "1960-03-15" }, "INELIGIBLE"],
  ] as const) {
    const response = await request.post(
      `${apiOrigin}/api/v1/eligibility/notices/${fixture.noticeId}/evaluate`,
      { data: { applicant } },
    );
    expect(response.ok()).toBeTruthy();
    expect((await response.json()).overall).toBe(overall);
  }
  await page.goto(`/notices/${fixture.noticeId}`);
  await expect(
    page.getByRole("heading", { name: "E2E 청년 주거 신청 공고", exact: true }),
  ).toBeVisible();
  const pdf = page.waitForResponse((r) => r.url().includes(`/files/pdf1`) && r.ok());
  await page
    .getByRole("button", { name: /원문 p\.1/ })
    .first()
    .click();
  expect((await pdf).headers()["content-type"]).toContain("application/pdf");
  await expect(page.locator("canvas").first()).toBeVisible();
  await expect(
    page.getByText("근거 문장을 노란색으로 표시했어요", { exact: true }).first(),
  ).toBeAttached();
  if (test.info().project.name === "mobile") {
    await page.goBack();
    await expect(page.getByRole("dialog", { name: "공고 원문" })).toHaveCount(0);
  } else await page.getByRole("button", { name: "원문 닫기", exact: true }).last().click();
  await session(page, "u1");
  await page.goto(`/notices/${fixture.noticeId}`);
  await page.getByRole("button", { name: "신청 준비하기", exact: true }).click();
  await expect(page).toHaveURL(/\/me\/preparations\/[a-f0-9-]+$/);
  const preparationId = page.url().split("/").at(-1)!;
  await page.getByLabel("주민등록등본 준비 상태", { exact: true }).selectOption("DONE");
  await expect(page.getByText("서류 1개 중 1개 준비", { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByLabel("주민등록등본 준비 상태", { exact: true })).toHaveValue("DONE");
  await page.screenshot({ path: test.info().outputPath("preparation.png"), fullPage: true });
  const auth = await bearer(page);
  const favorites = `${apiOrigin}/api/users/me/favorites/notice/${fixture.noticeId}`;
  for (let i = 0; i < 2; i++)
    expect((await page.request.put(favorites, { headers: auth })).status()).toBe(204);
  expect(
    (
      await (
        await page.request.get(`${apiOrigin}/api/users/me/favorites`, { headers: auth })
      ).json()
    ).items,
  ).toHaveLength(1);
  await control(request, "reminders");
  await control(request, "reminders");
  await expect
    .poll(
      async () => {
        const r = await page.request.get(`${apiOrigin}/api/users/me/notifications`, {
          headers: auth,
        });
        return (await r.json()).items.filter((n: { type: string }) => n.type === "DEADLINE_D3")
          .length;
      },
      { timeout: 30_000 },
    )
    .toBe(1);
  await expect
    .poll(
      async () => {
        const r = await request.get(`${notificationOrigin}/_e2e/sent`, {
          headers: controlHeaders(),
        });
        const messages: string[] = await r.json();
        return messages.filter((m) => m.includes(fixture.noticeId)).length;
      },
      { timeout: 30_000 },
    )
    .toBe(1);
  await page.goto("/alerts");
  await page.getByText("E2E 청년 주거 신청 공고", { exact: false }).first().click();
  await expect(page).toHaveURL(new RegExp(`/notices/${fixture.noticeId}`));
  await control(request, "correction");
  await expect
    .poll(async () => {
      const result = await page.request.get(`${apiOrigin}/api/users/me/notifications`, {
        headers: auth,
      });
      return (await result.json()).items.filter((n: { type: string }) => n.type === "CORRECTED")
        .length;
    })
    .toBe(1);
  await page.goto(`/me/preparations/${preparationId}`);
  await expect(page.getByRole("heading", { name: "공고·서류를 다시 확인해 주세요" })).toBeVisible();
  await expect(page.getByLabel("정정된 주민등록표등본 준비 상태", { exact: true })).toHaveValue(
    "RECHECK_REQUIRED",
  );
  await page.getByRole("button", { name: "정정 내용을 확인했어요" }).click();
  await expect(page.getByLabel("정정된 주민등록표등본 준비 상태", { exact: true })).toHaveValue(
    "RECHECK_REQUIRED",
  );
  await page.getByLabel("정정된 주민등록표등본 준비 상태", { exact: true }).selectOption("DONE");
  await expect(page.getByRole("heading", { name: "공고·서류를 다시 확인해 주세요" })).toHaveCount(
    0,
  );
  await page.getByRole("button", { name: "제출했다고 표시", exact: true }).click();
  await expect(page.getByRole("button", { name: "준비 중으로 되돌리기" })).toBeVisible();
  await page.getByRole("button", { name: "보관", exact: true }).click();
  await page.getByRole("button", { name: "보관 전 상태로 복원" }).click();
  await expect(page.getByRole("button", { name: "준비 중으로 되돌리기" })).toBeVisible();
  await page.getByRole("button", { name: "준비 기록 삭제", exact: true }).click();
  await page.getByRole("button", { name: "삭제하기", exact: true }).click();
  await expect(page).toHaveURL(/\/me\/preparations$/);
  expect(
    (
      await (
        await page.request.get(`${apiOrigin}/api/users/me/favorites`, { headers: auth })
      ).json()
    ).items,
  ).toHaveLength(1);
});
