import { expect, test } from "@playwright/test";

test("인증 링크를 열면 로그인 없이 이메일 주소를 인증한다", async ({ page }) => {
  const token = "a".repeat(64);
  let calls = 0;
  await page.route("**/api/email-notifications/verify", async (route) => {
    calls++;
    expect(route.request().method()).toBe("POST");
    expect(route.request().postDataJSON()).toEqual({ token });
    expect(route.request().headers()).not.toHaveProperty("authorization");
    expect(route.request().headers()).not.toHaveProperty("cookie");
    await route.fulfill({ status: 204 });
  });
  await page.goto(`/email/verify#token=${token}`);
  await expect(page.getByText("이메일 주소를 인증했어요.", { exact: false })).toBeVisible();
  await expect(page).toHaveURL(/\/email\/verify$/);
  expect(calls).toBe(1);
});

test("이메일 인증번호를 요청하고 만료 후 다시 받아 인증한다", async ({ page }) => {
  await page.route("**/api/users/me", (route) =>
    route.fulfill({
      json: {
        id: "email-settings-member",
        nickname: "이메일 테스트",
        role: "USER",
        providers: ["GOOGLE"],
        email: null,
        termsAgreed: true,
      },
    }),
  );
  await page.clock.install();
  const empty = {
    email: null,
    verified: false,
    enabled: false,
    newNotice: false,
    deadline: false,
    reportAnswer: false,
    verification: null,
  };
  let status: Omit<typeof empty, "email" | "verification"> & {
    email: string | null;
    verification: {
      expiresAt: string;
      resendAt: string;
      serverTime: string;
      attemptsRemaining: number;
    } | null;
  } = empty;
  await page.route(
    /\/api\/users\/me\/email-notifications(?:\/(?:request-code|verify-code|edit))?$/,
    async (route) => {
      const pathname = new URL(route.request().url()).pathname;
      if (pathname.endsWith("/request-code")) {
        expect(route.request().postDataJSON()).toEqual({
          email: "member@example.com",
          consent: true,
        });
        const issuedAt = Date.now();
        status = {
          ...empty,
          email: "member@example.com",
          verification: {
            expiresAt: new Date(issuedAt + 300_000).toISOString(),
            resendAt: new Date(issuedAt + 60_000).toISOString(),
            serverTime: new Date(issuedAt).toISOString(),
            attemptsRemaining: 5,
          },
        };
      }
      if (pathname.endsWith("/verify-code")) {
        expect(route.request().postDataJSON()).toEqual({ code: "012345" });
        status = {
          ...status,
          verified: true,
          enabled: true,
          newNotice: true,
          deadline: true,
          reportAnswer: true,
          verification: null,
        };
      }
      if (pathname.endsWith("/edit")) status = empty;
      await route.fulfill({ json: status });
    },
  );
  await page.goto("/me/notifications");
  const address = page.getByRole("textbox", { name: "알림 받을 이메일" });
  await address.fill("member@example.com");
  const editableBackground = await address.evaluate(
    (input) => getComputedStyle(input).backgroundColor,
  );
  await page.getByRole("button", { name: "동의하고 인증번호 받기" }).click();
  await expect(address).toHaveJSProperty("readOnly", true);
  await expect(address).not.toHaveCSS("background-color", editableBackground);
  await expect(address).not.toHaveCSS("background-color", "rgba(0, 0, 0, 0)");
  const timer = page.getByRole("timer", { name: "인증번호 남은 시간" });
  await expect(timer).toHaveText(/^(05:00|04:59)$/);
  await page.clock.fastForward(300_000);
  await expect(timer).toHaveText("00:00");
  await expect(page.getByRole("button", { name: "인증하기" })).toBeDisabled();
  await page.getByRole("button", { name: "인증번호 다시 받기" }).click();
  await page.getByRole("textbox", { name: "인증번호 6자리" }).fill("012345");
  await page.getByRole("button", { name: "인증하기" }).click();
  await expect(page.getByText("이메일을 인증했어요.", { exact: false })).toBeVisible();
  await expect(page.getByRole("button", { name: "알림 설정 저장" })).toBeVisible();
  await page.getByRole("button", { name: "동의 철회", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "유지하기" }).click();
  await page.getByRole("button", { name: "이메일 수정하기" }).click();
  await expect(address).toBeEditable();
  await expect(address).toHaveValue("");
});
