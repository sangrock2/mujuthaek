import { expect, test } from "@playwright/test";
import type { SearchItem } from "../src/features/homes/search";

test("주거 공고 목록 스크롤로 다음 페이지를 불러오고 실패한 페이지를 다시 시도한다", async ({
  page,
}, testInfo) => {
  const desktop = testInfo.project.name === "desktop";
  const items: SearchItem[] = Array.from({ length: 21 }, (_, i) => ({
    id: `test-notice-${i + 1}`,
    title: `스크롤 검증 공고 ${i + 1}`,
    provider: "GH",
    noticeType: "NATIONAL_RENTAL",
    regionCode: null,
    regionName: null,
    status: "APPLYING",
    applyStart: null,
    applyEnd: null,
    dday: 5,
    overall: "ELIGIBLE",
    prepareCostWon: null,
    prepareCostNote: null,
    areaScore: null,
    tags: [],
    siteCount: 1,
  }));
  const cursors: Array<string | null> = [];
  let pageTwoAvailable = false;
  await page.route("**/api/v1/notices/search", (route) => {
    const { cursor } = route.request().postDataJSON();
    cursors.push(cursor);
    if (cursor && !pageTwoAvailable) return route.fulfill({ status: 400, json: {} });
    return route.fulfill({
      json: {
        counts: { eligible: items.length, needsInput: 0, ineligible: 0 },
        items: cursor ? items.slice(20) : items.slice(0, 20),
        nextCursor: cursor ? null : "next",
        hasNext: !cursor,
      },
    });
  });

  await page.goto("/homes");
  const results = desktop
    ? page.getByRole("region", { name: "공고 목록", exact: true })
    : page.getByRole("main");
  await expect(results.getByText(items[0].title, { exact: true })).toBeVisible();
  expect(cursors).toEqual([null]);
  const title = page.getByRole("heading", { name: "주거 공고", exact: true });
  const titlePosition = await title.boundingBox();

  if (desktop) await results.hover();
  else await page.mouse.move(190, 500);
  await page.mouse.wheel(0, 15000);
  await expect(results.getByText("다음 공고 목록을 불러오지 못했어요")).toBeVisible();
  await expect(results.getByText(items[0].title, { exact: true })).toBeAttached();
  pageTwoAvailable = true;
  await results.getByRole("button", { name: "다시 시도", exact: true }).click();
  await expect(results.getByText(items.at(-1)!.title, { exact: true })).toBeAttached();
  await expect(results.getByText("다음 공고 목록을 불러오지 못했어요")).toHaveCount(0);
  expect(cursors.at(-1)).toBe("next");
  if (desktop) {
    expect(await title.boundingBox()).toEqual(titlePosition);
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
    await expect(page.getByRole("complementary", { name: "필터" })).toBeInViewport();
  }

  const view = page.getByRole("group", { name: "보기 방식" });
  await view.getByRole("button", { name: "지도", exact: true }).click();
  await expect(view.getByRole("button", { name: "지도", exact: true })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.getByRole("heading", { name: "공고 목록", exact: true })).toHaveCount(0);
  await expect(page.getByText(items[0].title, { exact: true })).toHaveCount(0);
  await view.getByRole("button", { name: "목록", exact: true }).click();
  await expect(page.getByText(items[0].title, { exact: true })).toBeAttached();
});

test("PC 공지의 목록과 본문은 별도로 스크롤된다", async ({ page }, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "PC에서만 두 영역이 동시에 표시됩니다.");
  await page.setViewportSize({ width: 1120, height: 620 });
  await page.goto("/announcements");
  const list = page.getByRole("region", { name: "공지 목록" });
  const detail = page.getByRole("article", { name: "공지 상세" });
  const heading = page.getByRole("heading", { name: "공지사항", exact: true });
  await expect(heading).toBeVisible();
  const titlePosition = await heading.boundingBox();
  const firstTitle = await detail.getByRole("heading").textContent();
  await detail.focus();
  await page.keyboard.press("End");
  await expect.poll(() => detail.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);
  expect(await list.evaluate((element) => element.scrollTop)).toBe(0);
  expect(await page.evaluate(() => window.scrollY)).toBe(0);
  expect(await heading.boundingBox()).toEqual(titlePosition);

  await detail.getByRole("button", { name: "다음 공지", exact: true }).click();
  await expect(detail.getByRole("heading")).not.toHaveText(firstTitle ?? "");
  expect(await detail.evaluate((element) => element.scrollTop)).toBe(0);
});
