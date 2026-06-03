import { expect, test, type Locator, type Page } from "@playwright/test";

import {
  dynamicConsoleRouteSamples,
  sidebarRouteInventory,
  staticConsoleRoutePaths,
} from "../src/app/routeInventory";
import {
  expectNoDocumentOverflow,
  expectNoRouteError,
  registerEnterpriseApiRoutes,
} from "./fixtures/enterpriseHarness";

type RuntimeErrors = {
  consoleErrors: string[];
  pageErrors: string[];
  requestFailures: string[];
};

type ControlSnapshot = {
  index: number;
  visibleIndex: number;
  matchIndex: number;
  label: string;
  tagName: string;
  role: string | null;
  href: string | null;
};

type RouteAuditResult = {
  path: string;
  scope: string;
  initialControls: number;
  primaryClicks: number;
  nestedClicks: number;
  skipped: string[];
};

const staticAuditPaths = staticConsoleRoutePaths.filter(
  (path) => !["/login", "/register", "/oauth/callback"].includes(path),
);
const auditPaths = [
  ...sidebarRouteInventory.map((item) => item.href),
  ...staticAuditPaths,
  ...dynamicConsoleRouteSamples.map((sample) => sample.sample),
].filter((path, index, paths) => paths.indexOf(path) === index);

const interactiveSelector = [
  "button",
  "a[href]",
  '[role="button"]',
  '[role="menuitem"]',
  '[role="switch"]',
  '[role="tab"]',
  '[role="option"]',
  '[role="combobox"]',
].join(",");

const shellInteractiveSelector = [
  "aside button",
  "aside a[href]",
  "header button",
  "header a[href]",
  '[aria-label="打开快捷操作"]',
  '[aria-label="关闭快捷操作"]',
].join(",");
const mainInteractiveSelector = `main ${interactiveSelector}`;
const nestedInteractiveSelector = [
  '[role="dialog"] button',
  '[role="dialog"] a[href]',
  '[role="menu"] button',
  '[role="menuitem"]',
  '[role="listbox"] [role="option"]',
].join(",");

const skipClickPatterns = [
  /注销|退出登录|Log out|Sign out/i,
  /重新加载|刷新页面|Reload page/i,
  /返回上一页|Back/i,
];

test.describe("full console menu and button interaction audit", () => {
  test("clicks shell menus and global controls without runtime failures", async ({ page }, testInfo) => {
    test.setTimeout(90_000);
    const result = await runAuditedRoute(page, "/", shellInteractiveSelector, "shell");

    const summary = {
      auditedRoutes: 1,
      totalInitialControls: result.initialControls,
      totalPrimaryClicks: result.primaryClicks,
      totalNestedClicks: result.nestedClicks,
      routes: [result],
    };
    await testInfo.attach("full-console-interaction-summary", {
      body: JSON.stringify(summary, null, 2),
      contentType: "application/json",
    });

    expect(result.primaryClicks).toBeGreaterThan(20);
  });

  for (const path of auditPaths) {
    test(`clicks page controls on ${path}`, async ({ page }, testInfo) => {
      test.setTimeout(180_000);
      const result = await runAuditedRoute(page, path, mainInteractiveSelector, "main");

      await testInfo.attach("full-console-interaction-summary", {
        body: JSON.stringify(result, null, 2),
        contentType: "application/json",
      });

      expect(result.initialControls).toBeGreaterThan(0);
      expect(result.primaryClicks + result.skipped.length).toBeGreaterThan(0);
    });
  }
});

async function runAuditedRoute(
  page: Page,
  path: string,
  controlSelector: string,
  scope: string,
): Promise<RouteAuditResult> {
  const runtimeErrors = trackRuntimeErrors(page);
  const harness = await registerEnterpriseApiRoutes(page);
  await page.setViewportSize({ width: 1440, height: 900 });

  const result = await auditRoute(page, path, controlSelector, scope);

  await harness.assertNoUnhandledApiRequests();
  expect(runtimeErrors).toEqual({ consoleErrors: [], pageErrors: [], requestFailures: [] });
  return result;
}

async function auditRoute(
  page: Page,
  path: string,
  controlSelector: string,
  scope: string,
): Promise<RouteAuditResult> {
  await openCleanRoute(page, path);
  if (scope === "shell") {
    await dismissBlockingGuidance(page);
  }
  const initialControls = await visibleControls(page.locator(controlSelector));
  const result: RouteAuditResult = {
    path,
    scope,
    initialControls: initialControls.length,
    primaryClicks: 0,
    nestedClicks: 0,
    skipped: [],
  };

  for (const control of initialControls) {
    if (shouldSkipControl(control)) {
      result.skipped.push(`${control.index}:${control.label}`);
      continue;
    }

    await openCleanRoute(page, path);
    if (scope === "shell") {
      await dismissBlockingGuidance(page);
    }
    const clicked = await clickControl(page, controlSelector, control);
    if (!clicked) {
      result.skipped.push(`${control.visibleIndex}:${control.label}:not-found-after-reload`);
      continue;
    }
    result.primaryClicks += 1;
    await assertPageStable(page);

    const nestedControls = await visibleControls(page.locator(nestedInteractiveSelector));
    for (const nested of nestedControls) {
      if (shouldSkipControl(nested)) {
        result.skipped.push(`${control.index}/${nested.index}:${nested.label}`);
        continue;
      }

      await openCleanRoute(page, path);
      if (scope === "shell") {
        await dismissBlockingGuidance(page);
      }
      const reopened = await clickControl(page, controlSelector, control);
      if (!reopened) continue;
      await assertPageStable(page);
      const nestedClicked = await clickNestedControl(page, nested);
      if (!nestedClicked) {
        result.skipped.push(`${control.visibleIndex}/${nested.visibleIndex}:${nested.label}:not-found-after-reopen`);
        continue;
      }
      result.nestedClicks += 1;
      await assertPageStable(page);
    }
  }

  return result;
}

async function openCleanRoute(page: Page, path: string): Promise<void> {
  if (page.url() !== "about:blank") {
    await page.goto("about:blank");
  }
  await page.goto(path);
  await assertPageStable(page);
}

async function assertPageStable(page: Page): Promise<void> {
  await page.waitForTimeout(100);
  await expectNoRouteError(page);
  await expect(page.locator("body")).not.toHaveText("");
  await expectNoDocumentOverflow(page);
}

async function dismissBlockingGuidance(page: Page): Promise<void> {
  const skipTour = page.getByRole("button", { name: /跳过导览|Skip tour/i });
  if (await skipTour.isVisible().catch(() => false)) {
    await skipTour.click();
    await page.waitForTimeout(100);
    await assertPageStable(page);
  }
}

async function visibleControls(locator: Locator): Promise<ControlSnapshot[]> {
  const snapshots = await locator.evaluateAll((elements) =>
    elements.map((element, index) => {
      const htmlElement = element as HTMLElement;
      const rect = htmlElement.getBoundingClientRect();
      const style = window.getComputedStyle(htmlElement);
      const disabled =
        htmlElement.hasAttribute("disabled") ||
        htmlElement.getAttribute("aria-disabled") === "true" ||
        (htmlElement as HTMLButtonElement).disabled === true;
      const hidden =
        rect.width < 1 ||
        rect.height < 1 ||
        Number(style.opacity) === 0 ||
        style.pointerEvents === "none" ||
        style.visibility === "hidden" ||
        style.display === "none" ||
        htmlElement.getAttribute("aria-hidden") === "true";
      const label =
        htmlElement.getAttribute("aria-label") ||
        htmlElement.getAttribute("title") ||
        htmlElement.textContent ||
        htmlElement.getAttribute("href") ||
        "";
      return {
        index,
        label: label.replace(/\s+/g, " ").trim(),
        tagName: htmlElement.tagName.toLowerCase(),
        role: htmlElement.getAttribute("role"),
        href: htmlElement instanceof HTMLAnchorElement ? htmlElement.href : null,
        disabled,
        hidden,
      };
    }),
  );
  const visibleSnapshots = snapshots
    .filter((snapshot) => !snapshot.disabled && !snapshot.hidden && snapshot.label.length > 0)
    .map(({ disabled: _disabled, hidden: _hidden, ...snapshot }, visibleIndex) => ({
      ...snapshot,
      visibleIndex,
      matchIndex: 0,
    }));

  const matchCounts = new Map<string, number>();
  return visibleSnapshots.map((snapshot) => {
    const signature = controlSignature(snapshot);
    const matchIndex = matchCounts.get(signature) ?? 0;
    matchCounts.set(signature, matchIndex + 1);
    return { ...snapshot, matchIndex };
  });
}

async function clickControl(page: Page, selector: string, target: ControlSnapshot): Promise<boolean> {
  const freshControls = await visibleControls(page.locator(selector));
  const signature = controlSignature(target);
  const freshTarget =
    freshControls.find((control) => controlSignature(control) === signature && control.matchIndex === target.matchIndex) ??
    freshControls[target.visibleIndex];
  if (!freshTarget) return false;
  return clickControlAtRawIndex(page, selector, freshTarget.index);
}

async function clickNestedControl(page: Page, target: ControlSnapshot): Promise<boolean> {
  return clickControl(page, nestedInteractiveSelector, target);
}

async function clickControlAtRawIndex(page: Page, selector: string, index: number): Promise<boolean> {
  const controls = page.locator(selector);
  if ((await controls.count()) <= index) return false;
  return clickIfVisible(controls.nth(index));
}

async function clickIfVisible(locator: Locator): Promise<boolean> {
  if (!(await locator.isVisible().catch(() => false))) return false;
  await locator.scrollIntoViewIfNeeded().catch(() => undefined);
  try {
    await locator.click({ timeout: 2_000 });
  } catch {
    return false;
  }
  return true;
}

function shouldSkipControl(control: ControlSnapshot): boolean {
  if (control.href && shouldSkipHref(control.href)) {
    return true;
  }
  return skipClickPatterns.some((pattern) => pattern.test(control.label));
}

function shouldSkipHref(href: string): boolean {
  if (!/^https?:\/\//i.test(href)) return false;
  const url = new URL(href);
  if (!["127.0.0.1", "localhost"].includes(url.hostname)) return true;
  return url.pathname === "/metrics" || url.pathname.startsWith("/api/");
}

function controlSignature(control: Pick<ControlSnapshot, "href" | "label" | "role" | "tagName">): string {
  const hrefPath = control.href ? safeHrefPath(control.href) : "";
  return [
    control.tagName,
    control.role ?? "",
    hrefPath,
    control.label.replace(/\s+/g, " ").trim(),
  ].join("|");
}

function safeHrefPath(href: string): string {
  try {
    const url = new URL(href);
    return `${url.pathname}${url.search}${url.hash}`;
  } catch {
    return href;
  }
}

function trackRuntimeErrors(page: Page): RuntimeErrors {
  const runtimeErrors: RuntimeErrors = { consoleErrors: [], pageErrors: [], requestFailures: [] };
  page.on("pageerror", (error) => runtimeErrors.pageErrors.push(error.message));
  page.on("requestfailed", (request) => {
    const failure = request.failure();
    if (!failure) return;
    if (failure.errorText === "net::ERR_ABORTED" && isLoopbackApiUrl(request.url())) return;
    runtimeErrors.requestFailures.push(`${request.method()} ${request.url()} ${failure.errorText}`);
  });
  page.on("console", (message) => {
    if (message.type() !== "error") return;
    const text = message.text();
    if (text.includes("Failed to load resource")) return;
    runtimeErrors.consoleErrors.push(text);
  });
  return runtimeErrors;
}

function isLoopbackApiUrl(rawUrl: string): boolean {
  try {
    const url = new URL(rawUrl);
    return ["127.0.0.1", "localhost"].includes(url.hostname) && url.pathname.startsWith("/api/");
  } catch {
    return false;
  }
}
