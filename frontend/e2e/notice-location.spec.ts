import { expect, test } from "@playwright/test";
import { reset } from "./support";

for (const hasUnits of [false, true]) {
  test(`좌표가 있는 공고는 호별 목록 ${hasUnits ? "조회가 비어도" : "자체가 없어도"} 지도를 보여준다`, async ({
    page,
    request,
  }) => {
    const fixture = await reset(request);
    await page.route(`**/api/v1/notices/${fixture.noticeId}`, async (route) => {
      const response = await route.fetch();
      const detail = await response.json();
      await route.fulfill({
        response,
        json: {
          ...detail,
          hasUnits,
          sites: [
            {
              id: "location-only",
              kind: "COMPLEX",
              name: "지도 회귀 시험 단지",
              address: "합성 시험 주소",
              regionCode: "1111000000",
              lat: 37.58,
              lng: 126.98,
            },
          ],
        },
      });
    });
    await page.route(`**/api/v1/notices/${fixture.noticeId}/units*`, (route) =>
      route.fulfill({ json: { items: [], hasNext: false, nextCursor: null } }),
    );
    const unitsResponse = hasUnits
      ? page.waitForResponse((response) =>
          new URL(response.url()).pathname.endsWith(`/notices/${fixture.noticeId}/units`),
        )
      : null;
    await page.goto(`/notices/${fixture.noticeId}`);
    if (unitsResponse) expect((await unitsResponse).ok()).toBeTruthy();
    const section = page.getByRole("region", { name: "공고 위치", exact: true });
    await expect(section).toBeVisible();
    await expect(section.getByLabel("단지 위치 지도", { exact: true })).toHaveCount(1);
    await expect(section).toContainText("호별 주택 목록과 별도로 확인한 위치");
    // The disposable E2E environment has no provider key. This verifies page wiring,
    // not a real Kakao request or a production coordinate mutation.
  });
}
