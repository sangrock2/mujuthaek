import { expect, test } from "@playwright/test";

test.use({ javaScriptEnabled: false });

for (const [path, title] of [
  ["/privacy", "개인정보처리방침"],
  ["/terms", "이용약관"],
] as const) {
  test(`${title} is public, complete, and readable without JavaScript`, async ({ page }) => {
    const response = await page.goto(path);
    expect(response?.status()).toBe(200);
    await expect(page.getByRole("heading", { level: 1, name: title })).toBeVisible();
    await expect(page.locator("article")).toContainText("무주택자들");
    await expect(page.locator("article")).toContainText("towo2ssss@gmail.com");
    await expect(page.locator("main")).toContainText("2026년 11월 14일");
    await expect(page.locator("main")).not.toContainText("게시할 예정이에요");
    await expect(page.locator("main")).not.toContainText("[회사명]");
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
      "href",
      `https://mujuthaek.vercel.app${path}`,
    );
    await expect(page.getByRole("navigation", { name: "문서 목차" })).toBeVisible();
    if (path === "/privacy") {
      await expect(page.locator("article")).toContainText("국외");
      await expect(page.locator("article")).toContainText("로컬 복구 사본은 자동 만료되지 않고");
      await expect(page.locator("article")).toContainText("날짜별 해시");
    } else {
      await expect(page.locator("article")).toContainText("만 14세 이상");
      await expect(page.locator("article")).toContainText("고의·중대한 과실");
      await expect(page.locator("article")).toContainText(
        "모든 손해에 대해 책임을 지지 않는다고 정하지 않습니다",
      );
    }
  });
}
