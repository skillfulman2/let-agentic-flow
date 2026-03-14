import { test, expect } from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';

test.describe('Accessibility Tests', () => {
  test('no critical accessibility violations', async ({ page }) => {
    await page.goto('/');
    const results = await new AxeBuilder({ page }).analyze();
    const critical = results.violations.filter((v) => v.impact === 'critical');
    expect(critical, 'Critical a11y violations found').toEqual([]);
  });

  test('no serious accessibility violations', async ({ page }) => {
    await page.goto('/');
    const results = await new AxeBuilder({ page }).analyze();
    const serious = results.violations.filter((v) => v.impact === 'serious');
    expect(serious, 'Serious a11y violations found').toEqual([]);
  });

  test('total violations under threshold', async ({ page }) => {
    await page.goto('/');
    const results = await new AxeBuilder({ page }).analyze();
    const summary = {
      critical: results.violations.filter((v) => v.impact === 'critical').length,
      serious: results.violations.filter((v) => v.impact === 'serious').length,
      moderate: results.violations.filter((v) => v.impact === 'moderate').length,
      minor: results.violations.filter((v) => v.impact === 'minor').length,
    };
    console.log('A11y violations:', JSON.stringify(summary));
    const total = summary.critical + summary.serious + summary.moderate + summary.minor;
    expect(total).toBeLessThan(20);
  });
});
