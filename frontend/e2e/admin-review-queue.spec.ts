import { expect, test, type Page, type Route } from "@playwright/test";

const firstId = "00000000-0000-4000-8000-00000000a111";
const secondId = "00000000-0000-4000-8000-00000000a112";
const item = (id: string, title: string) => ({
  id,
  title,
  kind: "NOTICE",
  reason: "MUST",
  sourceCode: "TEST",
  rawVersion: 1,
  queuedAt: "2026-11-19T00:00:00+09:00",
});

async function mockAdmin(page: Page, queue: (route: Route) => Promise<void>) {
  await page.route("**/api/**", async (route) => {
    const pathname = new URL(route.request().url()).pathname;
    if (pathname === "/api/admin/reviews/queue") return queue(route);
    if (pathname === "/api/admin/me") {
      return route.fulfill({
        json: {
          id: "00000000-0000-4000-8000-00000000ad01",
          nickname: "합성 검수 관리자",
          role: "SUPER_ADMIN",
          permissions: ["NOTICE_REVIEW"],
          active: true,
          freeze: null,
        },
      });
    }
    if (pathname.endsWith("/counts")) {
      return route.fulfill({
        json: {
          reviewPending: 0,
          benefitPending: 0,
          newCount: 0,
          pendingMessages: 0,
          pending: 0,
        },
      });
    }
    if (pathname === "/api/admin/sources") {
      return route.fulfill({ json: { summary: { fail: 0, late: 0, paused: 0 } } });
    }
    if (
      pathname === `/api/admin/reviews/${firstId}` ||
      pathname === `/api/admin/reviews/${secondId}`
    ) {
      return route.fulfill({
        json: {
          id: pathname.split("/").at(-1),
          reason: "MUST",
          title: "합성 검수 항목",
          field: "HOUSING",
          provider: null,
          sourceCode: "TEST",
          rawVersion: 1,
          receivedAt: "2026-11-19T00:00:00+09:00",
          detailUrl: null,
          issues: [],
          fields: [],
          sources: [],
          impact: null,
          log: [],
        },
      });
    }
    return route.fulfill({ status: 401, json: { status: 401 } });
  });
}

test("검수 조회 실패를 0건으로 표시하지 않고 수동 재시도로 복구한다", async ({ page }) => {
  let available = false;
  await mockAdmin(page, (route) =>
    available
      ? route.fulfill({
          json: { total: 1, items: [item(firstId, "복구된 검수 항목")], nextCursor: null },
        })
      : route.fulfill({ status: 503, json: { status: 503 } }),
  );
  await page.goto("/admin/review");
  const queue = page.getByRole("region", { name: "검수 대기열", exact: true });
  await expect(queue.getByRole("alert")).toContainText("검수 목록을 불러오지 못했어요");
  await expect(queue).toContainText("대기열 확인 필요");
  await expect(queue).not.toContainText("대기열 0건");
  await expect(queue).not.toContainText("검수할 항목이 없어요");
  available = true;
  await queue.getByRole("button", { name: "검수 목록 다시 불러오기", exact: true }).click();
  await expect(queue).toContainText("대기열 1건");
  await expect(queue).toContainText("복구된 검수 항목");
  await expect(queue.getByRole("alert")).toHaveCount(0);
});

test("정상 조회된 빈 검수 목록은 0건으로 표시한다", async ({ page }) => {
  await mockAdmin(page, (route) =>
    route.fulfill({ json: { total: 0, items: [], nextCursor: null } }),
  );
  await page.goto("/admin/review");
  const queue = page.getByRole("region", { name: "검수 대기열", exact: true });
  await expect(queue).toContainText("대기열 0건");
  await expect(queue).toContainText("검수할 항목이 없어요");
  await expect(queue.getByRole("alert")).toHaveCount(0);
});

test("원공고와 정정공고를 대기 한 건으로 표시하고 각 검수 문서를 열 수 있다", async ({ page }) => {
  await mockAdmin(page, (route) =>
    route.fulfill({
      json: {
        total: 1,
        items: [
          {
            ...item(firstId, "가상 임대주택 모집"),
            noticeGroupId: "source-1",
            members: [
              { id: firstId, title: "가상 임대주택 모집", rawVersion: 1, sourceKind: "NOTICE" },
              { id: secondId, title: "접수일 정정", rawVersion: 1, sourceKind: "CORRECTION" },
            ],
          },
        ],
        nextCursor: null,
      },
    }),
  );
  await page.goto("/admin/review");
  const queue = page.getByRole("region", { name: "검수 대기열", exact: true });
  await expect(queue).toContainText("대기열 1건");
  await expect(queue).toContainText("검수 문서 2건 남음");
  await expect(queue.getByRole("button", { name: /접수일 정정/ })).toHaveCount(0);
  const choice = page.getByLabel("이 공고의 검수 문서");
  await expect(choice).toHaveValue(`n:${firstId}`);
  const requested = page.waitForResponse((response) =>
    new URL(response.url()).pathname.endsWith(`/admin/reviews/${secondId}`),
  );
  await choice.selectOption(`n:${secondId}`);
  expect((await requested).status()).toBe(200);
  await expect(queue).toContainText("대기열 1건");
});

test("승인·반려 직후 처리 문서가 빠지고 공개 결과를 확인할 수 있다", async ({ page }) => {
  const eventId = "00000000-0000-4000-8000-00000000e111";
  await mockAdmin(page, (route) =>
    route.fulfill({
      json: {
        total: 1,
        items: [
          {
            ...item(firstId, "가상 임대주택 모집"),
            noticeGroupId: "source-1",
            members: [
              { id: firstId, title: "가상 임대주택 모집", rawVersion: 1, sourceKind: "NOTICE" },
              { id: secondId, title: "접수일 정정", rawVersion: 1, sourceKind: "CORRECTION" },
            ],
          },
        ],
        nextCursor: null,
      },
    }),
  );
  await page.route(`**/api/admin/reviews/${firstId}/approve`, (route) =>
    route.fulfill({ json: { id: firstId, reviewStatus: "APPROVED", eventId } }),
  );
  await page.route(`**/api/admin/reviews/${secondId}/reject`, (route) =>
    route.fulfill({ json: { id: secondId, reviewStatus: "REJECTED", eventId: null } }),
  );
  await page.route(`**/api/admin/reviews/publication/${eventId}`, (route) =>
    route.fulfill({ json: { outcome: "NEW_VERSION", publicId: firstId, version: 2 } }),
  );
  page.on("dialog", (dialog) => dialog.accept());

  await page.goto("/admin/review");
  const queue = page.getByRole("region", { name: "검수 대기열", exact: true });
  const choice = page.getByLabel("이 공고의 검수 문서");
  await page.getByRole("button", { name: "승인", exact: true }).click();
  await expect(choice).toHaveValue(`n:${secondId}`);
  await expect(choice.locator("option")).toHaveCount(1);
  await expect(queue).toContainText("검수 문서 1건 남음");
  await expect(page.getByRole("link", { name: "공개 공고 보기" })).toHaveAttribute(
    "href",
    `/notices/${firstId}`,
  );
  await expect(page.getByRole("status")).toContainText("공개 버전 2");

  await page.getByRole("button", { name: "반려", exact: true }).click();
  await expect(queue).toContainText("대기열 0건");
  await expect(queue).not.toContainText("가상 임대주택 모집");
  await expect(queue).toContainText("검수할 항목이 없어요");
});

test("다음 페이지 실패 시 기존 건수를 유지하고 실패한 페이지만 재시도한다", async ({ page }) => {
  let nextAvailable = false;
  let firstPageRequests = 0;
  let nextPageRequests = 0;
  await mockAdmin(page, (route) => {
    if (!new URL(route.request().url()).searchParams.has("cursor")) {
      firstPageRequests++;
      return route.fulfill({
        json: { total: 21, items: [item(firstId, "기존 검수 항목")], nextCursor: "test-next" },
      });
    }
    nextPageRequests++;
    return nextAvailable
      ? route.fulfill({
          json: { total: 21, items: [item(secondId, "다음 페이지 검수 항목")], nextCursor: null },
        })
      : route.fulfill({ status: 503, json: { status: 503 } });
  });
  await page.goto("/admin/review");
  const queue = page.getByRole("region", { name: "검수 대기열", exact: true });
  await expect(queue.getByRole("alert")).toBeVisible();
  await expect(queue).toContainText("대기열 21건");
  await expect(queue).toContainText("기존 검수 항목");
  nextAvailable = true;
  await queue.getByRole("button", { name: "검수 목록 다시 불러오기", exact: true }).click();
  await expect(queue).toContainText("다음 페이지 검수 항목");
  await expect(queue.getByRole("alert")).toHaveCount(0);
  expect(firstPageRequests).toBe(1);
  expect(nextPageRequests).toBe(2);
});
