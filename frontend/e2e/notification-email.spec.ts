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

test("개인정보 설정에서 이메일을 인증하고 알림 설정에서 수신 상태를 확인한다", async ({ page }) => {
  let contactEmail: string | null = "account@example.com";
  await page.route("**/api/users/me/email", async (route) => {
    if (route.request().method() === "DELETE") {
      contactEmail = null;
    } else {
      expect(route.request().method()).toBe("PUT");
      expect(route.request().postDataJSON()).toEqual({
        email: "member@example.com",
        consentVersion: "email-v1",
      });
      contactEmail = "member@example.com";
    }
    await route.fulfill({ status: 204 });
  });
  await page.route("**/api/users/me", (route) =>
    route.fulfill({
      json: {
        id: "email-settings-member",
        nickname: "이메일 테스트",
        role: "USER",
        providers: ["GOOGLE"],
        email: contactEmail,
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
      if (route.request().method() === "PUT") {
        expect(route.request().postDataJSON()).toEqual({
          enabled: true,
          newNotice: false,
          deadline: true,
          reportAnswer: true,
          consent: false,
        });
        status = { ...status, newNotice: false };
      }
      if (pathname.endsWith("/edit")) status = empty;
      await route.fulfill({ json: status });
    },
  );
  await page.goto("/me/notifications");
  await expect(page.getByRole("status").filter({ hasText: "미등록" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "이메일 주소" })).toHaveCount(0);
  await page.getByRole("link", { name: "개인정보 설정에서 관리" }).click();
  await expect(page).toHaveURL(/\/me\/privacy$/);
  const address = page.getByRole("textbox", { name: "이메일 주소" });
  await expect(page.locator('input[type="email"]')).toHaveCount(1);
  await expect(address).toHaveValue("account@example.com");
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
  const emailCard = page.getByRole("region", { name: "이메일", exact: true });
  await emailCard.getByText("계정 안내에 이메일 사용", { exact: true }).click();
  await expect(emailCard.getByText("account@example.com", { exact: true })).toBeVisible();
  expect(contactEmail).toBe("account@example.com");
  await expect(page.locator('input[type="email"]')).toHaveCount(1);
  await emailCard.getByRole("checkbox", { name: "연락용 이메일 수집·이용 동의" }).check();
  await emailCard.getByRole("button", { name: "이 주소를 계정 안내에 사용" }).click();
  await expect(
    emailCard.getByText("이 주소를 계정 안내에도 사용해요.", { exact: true }),
  ).toBeVisible();
  expect(contactEmail).toBe("member@example.com");
  await emailCard.getByRole("button", { name: "계정 안내 동의 철회" }).click();
  await expect(
    emailCard.getByText("계정 안내 이메일 동의를 철회했어요.", { exact: true }),
  ).toBeVisible();
  expect(contactEmail).toBeNull();
  await expect(address).toHaveValue("member@example.com");
  await page.goBack();
  await expect(page).toHaveURL(/\/me\/notifications$/);
  await expect(page.getByRole("status").filter({ hasText: "수신 중" })).toBeVisible();
  await expect(page.getByRole("textbox", { name: "이메일 주소" })).toHaveCount(0);
  await page.getByRole("link", { name: "개인정보 설정에서 관리" }).click();
  await expect(page.getByRole("checkbox", { name: "맞춤 신규 공고·지원 소식" })).toBeChecked();
  await page.getByRole("checkbox", { name: "맞춤 신규 공고·지원 소식" }).uncheck();
  await page.getByRole("button", { name: "알림 설정 저장" }).click();
  await expect(page.getByText("이메일 알림 설정을 저장했어요.", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "동의 철회", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await expect(dialog).toBeVisible();
  await dialog.getByRole("button", { name: "유지하기" }).click();
  await page.getByRole("button", { name: "이메일 수정하기" }).click();
  await expect(address).toBeEditable();
  await expect(address).toHaveValue("");
  await page.goBack();
  await expect(page.getByRole("status").filter({ hasText: "미등록" })).toBeVisible();
});
