import { test, expect } from '@playwright/test';

const BASE_URL = 'http://localhost:8081';

test.describe('Dashboard E2E - Smoke Tests', () => {

  test('page loads with correct title', async ({ page }) => {
    await page.goto(BASE_URL);
    await expect(page).toHaveTitle(/Application Tracker/i);
  });

  test('header stats are visible', async ({ page }) => {
    await page.goto(BASE_URL);
    await expect(page.locator('.header-stats')).toBeVisible();
    await expect(page.locator('.stat-chip').first()).toBeVisible();
  });

  test('toolbar is visible with status filter chips', async ({ page }) => {
    await page.goto(BASE_URL);
    await expect(page.locator('.toolbar')).toBeVisible();
    await expect(page.locator('.chip').first()).toBeVisible();
  });

  test('table renders with data from seeder', async ({ page }) => {
    await page.goto(BASE_URL);
    await expect(page.locator('table')).toBeVisible({ timeout: 10000 });
    await expect(page.locator('table tbody tr').first()).toBeVisible();
  });

});
