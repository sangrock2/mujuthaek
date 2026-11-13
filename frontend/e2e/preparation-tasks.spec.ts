import { expect, test } from "@playwright/test";
import { reset, session, bearer, apiOrigin } from "./support";

test("내 할 일을 추가·기한순 정렬·완료·수정·삭제하고 다음에도 이어서 본다", async ({
  page,
  request,
}) => {
  const { noticeId } = await reset(request);
  await page.clock.setFixedTime(new Date("2026-11-12T02:05:00Z"));
  await session(page, "u1");
  const auth = await bearer(page);
  const created = await page.request.put(
    `${apiOrigin}/api/users/me/preparations/notices/${noticeId}`,
    { headers: auth },
  );
  expect(created.status()).toBe(201);
  const preparation = await created.json();
  await page.goto(`/me/preparations/${preparation.id}`);
  const filters = page.getByLabel("할 일 필터", { exact: true }).getByRole("button");
  await expect(filters).toHaveText(["전체 0", "진행 중 0", "완료 0", "기한 지남 0"]);
  await expect(filters.first()).toHaveAttribute("aria-pressed", "true");
  await page.getByLabel("새 할 일", { exact: true }).fill("신청 사이트 가입 및 본인 인증");
  await page.getByLabel("기한 (선택)", { exact: true }).fill("2026-11-12");
  await page.getByRole("button", { name: "할 일 추가", exact: true }).click();
  await expect(
    page.getByRole("checkbox", { name: "신청 사이트 가입 및 본인 인증 완료", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("오늘까지", { exact: true })).toBeVisible();
  await page.getByLabel("새 할 일", { exact: true }).fill("준비 서류 발급");
  await page.getByLabel("기한 (선택)", { exact: true }).fill("2026-11-11");
  await page.getByRole("button", { name: "할 일 추가", exact: true }).click();
  await expect(page.getByLabel("할 일 정렬", { exact: true })).toHaveValue("created");
  await expect(page.getByRole("checkbox").first()).toHaveAccessibleName(
    "신청 사이트 가입 및 본인 인증 완료",
  );
  await page.getByLabel("할 일 정렬", { exact: true }).selectOption("due");
  await expect(page.getByRole("checkbox").first()).toHaveAccessibleName("준비 서류 발급 완료");
  await page.getByRole("button", { name: "기한 지남 1", exact: true }).click();
  await expect(page.getByRole("checkbox")).toHaveCount(1);
  await expect(page.getByRole("checkbox")).toHaveAccessibleName("준비 서류 발급 완료");
  await page.getByRole("checkbox", { name: "준비 서류 발급 완료", exact: true }).check();
  await expect(page.getByRole("button", { name: "기한 지남 0", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "완료 1", exact: true }).click();
  await expect(
    page.getByRole("checkbox", { name: "준비 서류 발급 완료", exact: true }),
  ).toBeChecked();
  await page.getByRole("button", { name: "준비 서류 발급 수정", exact: true }).click();
  await page.getByLabel("할 일 수정", { exact: true }).fill("서류 발급 후 내용 확인");
  await page.getByLabel("기한 수정 (선택)", { exact: true }).fill("");
  await page.getByRole("button", { name: "수정 저장", exact: true }).click();
  await expect(
    page.getByRole("checkbox", { name: "서류 발급 후 내용 확인 완료", exact: true }),
  ).toBeChecked();
  await page.reload();
  await page.getByRole("button", { name: "완료 1", exact: true }).click();
  await expect(
    page.getByRole("checkbox", { name: "서류 발급 후 내용 확인 완료", exact: true }),
  ).toBeChecked();
  await page.getByRole("button", { name: "서류 발급 후 내용 확인 삭제", exact: true }).click();
  await page.getByRole("button", { name: "할 일 삭제하기", exact: true }).click();
  await expect(
    page.getByRole("checkbox", { name: "서류 발급 후 내용 확인 완료", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "진행 중 1", exact: true }).click();
  await expect(
    page.getByRole("checkbox", { name: "신청 사이트 가입 및 본인 인증 완료", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "신청 방법과 문의처", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "신청 전 확인할 조건", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "공고에 나온 주거 비용", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("100만 원", { exact: true })).toBeVisible();
  await page.screenshot({ path: test.info().outputPath("task-checklist.png"), fullPage: true });
});
