import { expect, test } from "@playwright/test";

test("개인정보 설정에서 닉네임을 바꾸고 검색 기록 보관을 제어한다", async ({ page }) => {
  let nickname = "이전 이름";
  await page.route("**/api/users/me", (route) =>
    route.fulfill({
      json: {
        id: "privacy-settings-member",
        nickname,
        role: "USER",
        providers: ["KAKAO"],
        email: null,
        termsAgreed: true,
      },
    }),
  );
  await page.route("**/api/users/me/nickname", (route) => {
    expect(route.request().method()).toBe("PUT");
    expect(route.request().postDataJSON()).toEqual({ nickname: "새 이름 🏡" });
    nickname = "새 이름 🏡";
    return route.fulfill({ json: { nickname } });
  });

  await page.goto("/me/privacy");
  const account = page.getByRole("region", { name: "계정 및 연동 정보" });
  await account.getByRole("button", { name: "닉네임 변경" }).click();
  const field = account.getByRole("textbox", { name: "새 닉네임" });
  const save = account.getByRole("button", { name: "저장", exact: true });
  await field.fill("한");
  await expect(save).toBeDisabled();
  await field.fill("  새 이름 🏡 ");
  await save.click();
  await expect(account.getByText("닉네임을 변경했어요.")).toBeVisible();
  await expect(account.getByText("새 이름 🏡", { exact: true })).toBeVisible();
  await page.goto("/me");
  await expect(
    page.getByRole("region", { name: "계정", exact: true }).getByText("새 이름 🏡님"),
  ).toBeVisible();

  async function search(keyword: string) {
    await page.goto("/search");
    const searchField = page.getByRole("searchbox");
    await searchField.fill(keyword);
    await searchField.press("Enter");
  }

  await search("임대주택");
  await page.goto("/me/privacy");
  await expect(page.getByText("저장된 검색어 1개", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "최근 검색어 지우기", exact: true }).click();
  await expect(page.getByText("저장된 검색어 0개", { exact: true })).toBeVisible();
  await search("보증금");
  await page.goto("/me/privacy");
  await expect(page.getByText("저장된 검색어 1개", { exact: true })).toBeVisible();
  const toggle = page.getByRole("switch", { name: "최근 검색어 저장" });
  await toggle.click();
  await expect(toggle).toHaveAttribute("aria-checked", "false");
  await expect(page.getByText("저장된 검색어 0개", { exact: true })).toBeVisible();
  await search("청년주택");
  await page.goto("/me/privacy");
  await expect(toggle).toHaveAttribute("aria-checked", "false");
  await expect(page.getByText("저장된 검색어 0개", { exact: true })).toBeVisible();
  await toggle.click();
  await search("국민임대");
  await page.goto("/me/privacy");
  await expect(page.getByText("저장된 검색어 1개", { exact: true })).toBeVisible();

  await page.getByRole("link", { name: "개인정보 열람·정정·삭제 요청 안내" }).click();
  await expect(page.getByRole("region", { name: "개인정보 권리 행사 안내" })).toBeVisible();
});
