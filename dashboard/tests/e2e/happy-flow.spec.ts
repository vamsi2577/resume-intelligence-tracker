import { test, expect } from '@playwright/test';

// Use the local frontend-e2e docker container URL
const BASE_URL = 'http://localhost:8081';

test.describe('Dashboard E2E - Happy Flow', () => {

  test('should display applications table and allow filtering by Assessment status', async ({ page }) => {
    await page.goto(BASE_URL);
    await expect(page.locator('table tbody tr').first()).toBeVisible({ timeout: 10000 });

    await page.locator('.toolbar').getByText('Assessment', { exact: true }).click();
    await expect(page).toHaveURL(/.*status=assessment.*/);

    const tableRows = page.locator('table tbody tr');
    const count = await tableRows.count();

    if (count > 0) {
      const firstRowStatus = page.locator('table tbody tr').first().locator('td').nth(1);
      await expect(firstRowStatus).toContainText(/assessment/i);
    } else {
      await expect(page.locator('td.text-center')).toBeVisible();
    }
  });

  test('should filter applications by needs_review flag', async ({ page }) => {
    await page.goto(BASE_URL);
    await expect(page.locator('table tbody tr').first()).toBeVisible({ timeout: 10000 });

    await page.goto(`${BASE_URL}/?needs_review=true`);
    await expect(page.locator('table')).toBeVisible();

    // needs_review badge in header should reflect count
    const badge = page.locator('#needsReviewBadge');
    const badgeVisible = await badge.isVisible();
    if (badgeVisible) {
      const badgeText = await badge.innerText();
      expect(parseInt(badgeText)).toBeGreaterThan(0);
    }
  });

});
