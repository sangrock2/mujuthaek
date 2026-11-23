import { expect, test } from "@playwright/test";
import { reset, session } from "./support";

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

test("인증 요청한 주소는 수정 버튼으로만 잠금을 해제한다", async ({ page, request }) => {
  await reset(request);
  await session(page, "u1");
  const empty: {
    email: string | null;
    verified: boolean;
    enabled: boolean;
    newNotice: boolean;
    deadline: boolean;
    reportAnswer: boolean;
  } = {
    email: null,
    verified: false,
    enabled: false,
    newNotice: false,
    deadline: false,
    reportAnswer: false,
  };
  let status = empty;
  await page.route(
    /\/api\/users\/me\/email-notifications(?:\/(?:request|edit))?$/,
    async (route) => {
      const pathname = new URL(route.request().url()).pathname;
      if (pathname.endsWith("/request")) {
        expect(route.request().postDataJSON()).toEqual({
          email: "member@example.com",
          consent: true,
        });
        status = { ...empty, email: "member@example.com" };
      }
      if (pathname.endsWith("/edit")) {
        expect(route.request().method()).toBe("POST");
        status = empty;
      }
      await route.fulfill({ json: status });
    },
  );
  await page.goto("/me/notifications");
  const address = page.getByRole("textbox", { name: "알림 받을 이메일" });
  await address.fill("member@example.com");
  await page.getByRole("checkbox", { name: /알림 이메일 수집/ }).check();
  await page.getByRole("button", { name: "동의하고 인증 메일 받기" }).click();
  await expect(address).toHaveJSProperty("readOnly", true);
  await expect(page.getByRole("button", { name: "동의 철회", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "이메일 수정하기" }).click();
  await expect(address).toBeEditable();
  await expect(address).toHaveValue("");
  await expect(page.getByText("이전 인증 링크가 만료됐어요.", { exact: false })).toBeVisible();
});
