import { expect, test } from "@playwright/test";

test("조건 미입력 회원도 내 홈에서 새 공고와 마감 일정을 본다", async ({ page }) => {
  await page.route("**/api/users/me", (route) =>
    route.fulfill({
      json: {
        id: "home-entry-member",
        nickname: "홈 테스트",
        role: "USER",
        providers: ["KAKAO"],
        email: null,
        termsAgreed: true,
      },
    }),
  );
  await page.route("**/api/v1/home/summary", (route) => {
    expect(route.request().postDataJSON()).toEqual({ filters: {}, applicant: {} });
    const notice = {
      id: "019380fe-33e1-7c2c-8903-bad597fffc07",
      title: "신규 주거 공고",
      provider: "LH",
      noticeType: "PUBLIC_RENT",
      regionName: "전국",
      status: "APPLYING",
      postedOn: "2026-11-24",
      applyEnd: "2026-11-26",
      dday: 2,
      overall: "NEEDS_INPUT",
    };
    return route.fulfill({
      json: {
        homes: { eligible: 0, needsInput: 1, ineligible: 0, newThisWeek: 1, closingSoon: 1 },
        benefits: { eligible: 0, needsInput: 1, annualAmountWon: 0 },
        suggestedBenefit: null,
        news: [notice],
        deadlines: [notice],
      },
    });
  });

  await page.goto("/");
  await page.getByRole("link", { name: "내 홈", exact: true }).click();
  await expect(page).toHaveURL(/\/home$/);
  const home = page.getByRole("main");
  await expect(home.getByRole("heading", { name: "내 홈", exact: true })).toBeVisible();
  await expect(home.getByRole("link", { name: /공고 둘러보기/ })).toHaveAttribute("href", "/homes");
  await expect(home.getByRole("link", { name: /혜택 둘러보기/ })).toHaveAttribute(
    "href",
    "/benefits",
  );
  await expect(home.getByRole("link", { name: /신규 주거 공고/ })).toHaveCount(2);
  await expect(home.getByText("지원 가능한 청약·공공임대", { exact: true })).toHaveCount(0);
  await expect(home.getByRole("link", { name: "내 조건 입력하기", exact: true })).toHaveAttribute(
    "href",
    "/profile",
  );
});
