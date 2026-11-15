import { expect, test } from "@playwright/test";
import { reset } from "./support";

test("일시적인 연결 장애가 해소되면 운영 시간 안내 없이 화면이 복구된다", async ({
  page,
  request,
}) => {
  await reset(request);
  let available = false;
  await page.route("**/api/**", (route) =>
    available
      ? route.continue()
      : route.fulfill({ status: 503, contentType: "text/plain", body: "Temporarily unavailable" }),
  );
  await page.goto("/login");
  const banner = page
    .getByRole("status")
    .filter({ hasText: "서버에 일시적으로 연결하지 못했어요" });
  await expect(banner).toBeVisible();
  await expect(page.getByText("서비스 운영 시간:")).toHaveCount(0);
  available = true;
  await expect(banner).not.toBeVisible({ timeout: 20000 });
  await expect(page.getByRole("link", { name: /카카오/ })).toBeVisible();
});
