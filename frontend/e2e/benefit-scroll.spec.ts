import { expect, test } from "@playwright/test";

const items = Array.from({ length: 26 }, (_, index) => ({
  id: `benefit-${index + 1}`,
  title: `테스트 주거 혜택 ${index + 1}`,
  agency: "테스트 기관",
  category: "HOUSING",
  regionNames: [],
  amountText: "주거비 지원",
  applyStatus: "ALWAYS",
  overall: "NEEDS_INPUT",
}));

test("혜택 스크롤에서 다음 페이지를 불러오고 선택한 분야는 첫 커서부터 조회한다", async ({
  page,
}, testInfo) => {
  const desktop = testInfo.project.name === "desktop";
  const requests: Array<{ category?: string; cursor: string | null }> = [];
  await page.route("**/api/v1/benefits/search", (route) => {
    const { filters, cursor } = route.request().postDataJSON();
    const category = filters.categories?.[0];
    requests.push({ category, cursor });
    return route.fulfill({
      json: {
        items:
          category === "TRANSPORT"
            ? [{ ...items[0], id: "transport-1", title: "테스트 교통비 혜택", category }]
            : cursor
              ? items.slice(20)
              : items.slice(0, 20),
        summary: { eligible: 0, needsInput: 27, ineligible: 0, annualAmountWon: 0 },
        categoryCounts: { HOUSING: 26, ASSET: 0, TRANSPORT: 1 },
        hasNext: !cursor && !category,
        nextCursor: !cursor && !category ? "page-2" : null,
      },
    });
  });
  await page.route("**/api/v1/benefits/*", (route) => {
    const id = new URL(route.request().url()).pathname.split("/").at(-1);
    if (id === "search") return route.fallback();
    const item = items.find((entry) => entry.id === id) ?? items[0];
    return route.fulfill({
      json: {
        header: item,
        supports: [],
        howToApply: "접수처에서 신청해 주세요",
        documents: ["확인용 서류"],
        conditions: Array.from({ length: 24 }, (_, index) => ({
          type: "GENERAL",
          rawText: `신청 자격 항목 ${index + 1}`,
        })),
        sources: [],
      },
    });
  });
  await page.route("**/api/v1/benefits/*/evaluate", (route) => route.fulfill({ status: 404 }));

  await page.goto("/benefits");
  const list = desktop ? page.getByRole("region", { name: "혜택 목록" }) : page.getByRole("main");
  await expect(list.getByText("테스트 주거 혜택 1", { exact: true })).toBeVisible();
  expect(requests).toEqual([{ category: undefined, cursor: null }]);

  if (desktop) {
    const detail = page.getByRole("region", { name: "혜택 상세" });
    await expect(
      detail.getByRole("heading", { name: "테스트 주거 혜택 1", exact: true }),
    ).toBeVisible();
    const top = await page.getByRole("heading", { name: "내 혜택", exact: true }).boundingBox();
    await detail.hover();
    await page.mouse.wheel(0, 4000);
    await expect.poll(() => detail.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);
    await expect(detail.getByText("접수처에서 신청해 주세요")).toBeInViewport();
    expect(await list.evaluate((element) => element.scrollTop)).toBe(0);
    expect(await page.evaluate(() => window.scrollY)).toBe(0);
    expect(await page.getByRole("heading", { name: "내 혜택", exact: true }).boundingBox()).toEqual(
      top,
    );
    expect(requests).toHaveLength(1);
    await list.hover();
  }
  await page.mouse.wheel(0, 10000);
  await expect(list.getByText("테스트 주거 혜택 26", { exact: true })).toBeAttached();
  expect(requests).toEqual([
    { category: undefined, cursor: null },
    { category: undefined, cursor: "page-2" },
  ]);

  if (desktop) {
    const item = list.getByRole("button", { name: /테스트 주거 혜택 25/ });
    await item.click();
    const detail = page.getByRole("region", { name: "혜택 상세" });
    await expect(
      detail.getByRole("heading", { name: "테스트 주거 혜택 25", exact: true }),
    ).toBeInViewport();
    expect(await detail.evaluate((element) => element.scrollTop)).toBe(0);
    expect(await list.evaluate((element) => element.scrollTop)).toBeGreaterThan(0);
    await expect(list.getByText("전체 27건")).toBeVisible();
    await expect(detail.getByText("25 / 27번째 확인 중")).toBeVisible();
    await detail.getByRole("button", { name: "다음 혜택" }).click();
    await expect(
      detail.getByRole("heading", { name: "테스트 주거 혜택 26", exact: true }),
    ).toBeInViewport();
    await expect(detail.getByText("26 / 27번째 확인 중")).toBeVisible();
    await detail.getByRole("button", { name: "이전 혜택" }).click();
    await expect(item).toHaveAttribute("aria-pressed", "true");
  }

  await page.getByRole("button", { name: "교통 1", exact: true }).click();
  await expect(list.getByText("테스트 교통비 혜택", { exact: true })).toBeVisible();
  await expect(list.getByText("테스트 주거 혜택 1", { exact: true })).toHaveCount(0);
  expect(requests.at(-1)).toEqual({ category: "TRANSPORT", cursor: null });
});
