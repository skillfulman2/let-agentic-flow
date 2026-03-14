import { test, expect } from '@playwright/test';

test.describe('PWA Tests', () => {
  test('manifest.json exists and has required fields', async ({ page }) => {
    const response = await page.goto('/manifest.json');
    expect(response?.status()).toBe(200);
    const manifest = await response?.json();
    expect(manifest).toHaveProperty('name');
    expect(manifest).toHaveProperty('icons');
    expect(manifest).toHaveProperty('start_url');
  });

  test('manifest is linked in HTML', async ({ page }) => {
    await page.goto('/');
    const manifestLink = await page.locator('link[rel="manifest"]').count();
    expect(manifestLink).toBeGreaterThan(0);
  });

  test('service worker registers', async ({ page }) => {
    await page.goto('/');
    // Give the service worker time to register
    await page.waitForTimeout(2000);
    const swRegistered = await page.evaluate(async () => {
      if (!('serviceWorker' in navigator)) return false;
      try {
        const reg = await navigator.serviceWorker.getRegistration();
        return reg !== undefined;
      } catch {
        return false;
      }
    });
    expect(swRegistered).toBe(true);
  });
});
