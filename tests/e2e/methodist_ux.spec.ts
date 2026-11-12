import { expect, test, type Page, type TestInfo } from "@playwright/test";

const RAW_UI_TOKENS = [
  "DEMO-M6", "cluster_robust_t_class", "target_hours", "gcd_lcm_confusion",
  "incomplete_factorization", "partial_condition", "adjusted_association",
];

async function login(page: Page) {
  await page.goto("/login");
  await page.getByTestId("enter-demo").click();
  await expect(page.getByTestId("topics-table")).toBeVisible({ timeout: 60_000 });
}

async function expectSpecialistLanguage(page: Page) {
  const visible = await page.locator("body").innerText();
  for (const token of RAW_UI_TOKENS) expect(visible, `technical token is visible: ${token}`).not.toContain(token);
}

async function expectFitsLaptop(page: Page) {
  const size = await page.evaluate(() => ({ viewport: document.documentElement.clientWidth, document: document.documentElement.scrollWidth }));
  expect(size.document, `horizontal overflow: ${size.document}px > ${size.viewport}px`).toBeLessThanOrEqual(size.viewport + 1);
}

test("a methodist can follow the core path without internal codes and keep a draft after F5", async ({ page }, testInfo: TestInfo) => {
  await page.setViewportSize({ width: 1280, height: 720 });
  await login(page);
  await expectSpecialistLanguage(page);
  await expectFitsLaptop(page);

  await page.getByTestId("open-topic-T3").click();
  await expect(page.getByTestId("topic-title")).toBeVisible();
  await expectSpecialistLanguage(page);
  await expectFitsLaptop(page);
  await page.screenshot({ path: testInfo.outputPath("topic-ru-1280x720.png"), fullPage: false });

  await page.getByRole("button", { name: "KZ" }).click();
  await expect(page.getByTestId("topic-title")).toBeVisible();
  await expectSpecialistLanguage(page);
  await expect(page.locator("body")).not.toContainText("Тапсырманың тақырыптағы салмағы: 1.00");
  await page.screenshot({ path: testInfo.outputPath("topic-kz-1280x720.png"), fullPage: false });
  await page.getByRole("button", { name: "RU" }).click();

  await page.getByRole("link", { name: "Сравнение пособий", exact: true }).click();
  await expect(page.getByText(/Единого лучшего пособия|Пособие/).first()).toBeVisible({ timeout: 30_000 });
  await expectSpecialistLanguage(page);
  await page.getByRole("button", { name: "Перейти к планированию часов" }).click();

  await expect(page.getByTestId("planner-table")).toBeVisible();
  await expect(page.getByText("Текущие ограничения уже заполнены")).toBeVisible();
  await expectFitsLaptop(page);
  await page.screenshot({ path: testInfo.outputPath("planner-1280x720.png"), fullPage: false });
  await page.getByTestId("solve").click();
  await expect(page.getByTestId("scenario-balanced")).toBeVisible({ timeout: 30_000 });
  await page.getByTestId("use-plan-balanced").click();
  await page.getByRole("button", { name: "Перейти к решению" }).click();

  await page.getByTestId("f-problem").fill("Ученикам трудно складывать дроби с разными знаменателями");
  await page.getByLabel("Гипотеза").fill("Не сформировано понимание общего знаменателя");
  await page.getByLabel("Действие").fill("Добавить практику и повторно проверить результат");
  await page.getByTestId("f-responsible").fill("Руководитель методического объединения");
  await page.reload();
  await expect(page.getByTestId("f-problem")).toHaveValue("Ученикам трудно складывать дроби с разными знаменателями");
  await expect(page.getByTestId("f-responsible")).toHaveValue("Руководитель методического объединения");
  await expectSpecialistLanguage(page);
  await page.screenshot({ path: testInfo.outputPath("decision-after-reload-1280x720.png"), fullPage: false });
});
