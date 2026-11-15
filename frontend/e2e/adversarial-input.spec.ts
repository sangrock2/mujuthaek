import { expect, test } from "@playwright/test";
import { apiOrigin, reset, session, bearer } from "./support";

test("저장된 할 일의 HTML·이벤트 코드를 실행하지 않고 글자로 보여 준다", async ({
  page,
  request,
}) => {
  const fixture = await reset(request);
  await session(page, "u1");
  const auth = await bearer(page);
  const created = await page.request.put(
    `${apiOrigin}/api/users/me/preparations/notice/${fixture.noticeId}`,
    { headers: auth },
  );
  expect(created.status()).toBe(201);
  const preparation = await created.json();
  const title = '<img src=x onerror="window.__securityCanary=1">';
  const saved = await page.request.post(
    `${apiOrigin}/api/users/me/preparations/${preparation.id}/tasks`,
    { headers: auth, data: { title, expectedRevision: preparation.revision } },
  );
  expect(saved.ok()).toBeTruthy();
  await page.goto(`/me/preparations/${preparation.id}`);
  await expect(page.getByRole("checkbox", { name: `${title} 완료`, exact: true })).toBeVisible();
  await expect(page.locator('img[src="x"]')).toHaveCount(0);
  expect(await page.evaluate(() => Reflect.get(window, "__securityCanary"))).toBeUndefined();
  await page.reload();
  await expect(page.getByRole("checkbox", { name: `${title} 완료`, exact: true })).toBeVisible();
  expect(await page.evaluate(() => Reflect.get(window, "__securityCanary"))).toBeUndefined();
});
