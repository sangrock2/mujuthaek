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
    await expect(page.locator("article")).toContainText(
      path === "/privacy" ? "contact@mujuthaek.store" : "towo2ssss@gmail.com",
    );
    await expect(page.locator("main")).toContainText(
      path === "/privacy" ? "2026년 11월 24일" : "2026년 11월 14일",
    );
    await expect(page.locator("main")).not.toContainText("게시할 예정이에요");
    await expect(page.locator("main")).not.toContainText("[회사명]");
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute(
      "href",
      `https://mujuthaek.store${path}`,
    );
    const toc = page.getByRole("navigation", { name: "문서 목차" });
    const body = page.getByRole("region", { name: "문서 본문" });
    const header = page.getByRole("banner");
    const headerBefore = await header.boundingBox();
    await expect(toc).toBeVisible();
    await expect(
      toc.getByRole("link", { name: /문의하거나|약관·정책 이력 보기|주요 내용/ }),
    ).toHaveCount(0);
    await toc.getByRole("link").nth(2).click();
    await expect.poll(() => body.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
    expect(await header.boundingBox()).toEqual(headerBefore);
    const menu = page.getByRole("navigation", { name: "고객센터 메뉴" });
    await expect(menu.getByRole("link")).toHaveCount(5);
    await expect(menu.getByRole("link", { name: title, exact: true })).toHaveAttribute(
      "aria-current",
      "page",
    );
    await expect(page.getByRole("link", { name: "약관·정책 이력 보기" })).toHaveAttribute(
      "href",
      "/legal",
    );
    if (path === "/privacy") {
      const help = page.getByRole("region", { name: "개인정보 권리 행사 안내" });
      await expect(help.getByRole("link", { name: "개인정보 설정 열기" })).toHaveAttribute(
        "href",
        "/me?tab=privacy",
      );
      await expect(help).toContainText("계정 안내 동의 철회");
      await expect(help).toContainText("재인증");
      await expect(help.getByRole("link", { name: "이메일로 권리 행사 요청하기" })).toHaveAttribute(
        "href",
        /^mailto:towo2ssss@gmail\.com\?subject=/,
      );
      await expect(page.locator("article")).toContainText("국외");
      await expect(page.locator("article")).toContainText("로컬 복구 사본은 자동 만료되지 않고");
      await expect(page.locator("article")).toContainText("날짜별 해시");
    } else {
      const main = page.locator("main");
      await expect(main.getByRole("heading", { name: "먼저 확인해 주세요" })).toHaveCount(0);
      const help = main.getByRole("region", { name: "서비스 문의와 이의 신청 안내" });
      await expect(
        help.getByRole("heading", { name: "문의하거나 이의를 신청하려면" }),
      ).toBeVisible();
      await expect(
        main.locator("article + div").getByRole("complementary", { name: "주요 내용" }),
      ).toBeAttached();
      await expect(
        main.locator("article + div").getByRole("region", { name: "서비스 문의와 이의 신청 안내" }),
      ).toBeAttached();
      await expect(page.locator("article")).toContainText("만 14세 이상");
      await expect(page.locator("article")).toContainText("고의·중대한 과실");
      await expect(page.locator("article")).toContainText(
        "모든 손해에 대해 책임을 지지 않는다고 정하지 않습니다",
      );
    }
  });
}

test("legal history preserves the published text and rejects nonexistent versions", async ({
  page,
}) => {
  await page.goto("/legal");
  await expect(page.getByRole("heading", { level: 1, name: "약관·정책 이력" })).toBeVisible();
  await expect(page.getByRole("region", { name: "변경 안내" })).toContainText(
    "v1.0 전문의 수집 항목·목적·보유기간·이용 조건은 변경하지 않았습니다",
  );
  for (const kind of ["privacy", "terms"]) {
    await expect(page.locator(`a[href="/legal/${kind}/1.0"]`)).toBeVisible();
  }
  await expect(page.locator('a[href="/legal/privacy/1.1"]')).toBeVisible();
  for (const kind of ["privacy", "terms"]) {
    await page.goto(`/${kind}`);
    const currentText = await page.locator("article").innerText();
    const response = await page.goto(`/legal/${kind}/${kind === "privacy" ? "1.2" : "1.0"}`);
    expect(response?.status()).toBe(200);
    expect(await page.locator("article").innerText()).toBe(currentText);
    await expect(page.getByRole("link", { name: "현재 적용 문서 보기" })).toHaveAttribute(
      "href",
      `/${kind}`,
    );
    await expect(page.locator('meta[name="robots"]')).toHaveAttribute("content", "noindex, follow");
  }
  expect((await page.goto("/legal/privacy/99.0"))?.status()).toBe(404);
  expect((await page.goto("/legal/unknown/1.0"))?.status()).toBe(404);
});

test.describe("published legal announcement", () => {
  test.use({ javaScriptEnabled: true });

  test("announcement opens the actual legal history", async ({ page }) => {
    await page.goto("/announcements");
    await page
      .getByRole("button", { name: /개인정보 권리 행사 안내와 약관·정책 이력을 확인하세요/ })
      .click();
    await expect(
      page.getByRole("heading", { name: "개인정보 권리 행사 안내와 약관·정책 이력을 확인하세요" }),
    ).toBeVisible();
    await page.getByRole("link", { name: "약관·정책 이력 보기" }).click();
    await expect(page.getByRole("heading", { level: 1, name: "약관·정책 이력" })).toBeVisible();
  });
});
