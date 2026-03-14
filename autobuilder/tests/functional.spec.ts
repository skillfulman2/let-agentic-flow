import { test, expect } from '@playwright/test';

test.describe('Functional Tests', () => {
  test('page loads with 200 status', async ({ page }) => {
    const response = await page.goto('/');
    expect(response?.status()).toBe(200);
  });

  test('no uncaught JS errors', async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.goto('/');
    await page.waitForTimeout(2000);
    expect(errors).toEqual([]);
  });

  test('page has a title', async ({ page }) => {
    await page.goto('/');
    const title = await page.title();
    expect(title.length).toBeGreaterThan(0);
  });

  test('all internal links resolve (no 404s)', async ({ page }) => {
    await page.goto('/');
    const links = await page.locator('a[href^="/"]').all();
    for (const link of links) {
      const href = await link.getAttribute('href');
      if (href) {
        const response = await page.goto(href);
        expect(response?.status(), `Link ${href} returned 404`).not.toBe(404);
        await page.goto('/');
      }
    }
  });

  test('responsive: no horizontal overflow at 375px', async ({ page }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto('/');
    const overflow = await page.evaluate(() => {
      return document.documentElement.scrollWidth > document.documentElement.clientWidth;
    });
    expect(overflow).toBe(false);
  });

  test('responsive: no horizontal overflow at 1280px', async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await page.goto('/');
    const overflow = await page.evaluate(() => {
      return document.documentElement.scrollWidth > document.documentElement.clientWidth;
    });
    expect(overflow).toBe(false);
  });
});
