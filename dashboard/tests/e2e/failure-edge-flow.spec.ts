import { test, expect } from '@playwright/test';

const BASE_URL = 'http://localhost:8081';

test.describe('Dashboard E2E - Failure & Edge Cases', () => {

  test('should handle completely bogus status filters gracefully', async ({ page }) => {
    // 1. Force the dashboard to route to an invalid status
    // The backend Enum strictly validates this, so it should return 422 Unprocessable Entity
    await page.goto(`${BASE_URL}/?status=invalid_status_xyz`);

    // 2. The frontend should gracefully handle the 422 error and maybe show an error toast or empty state
    // We expect the table to eventually render, but perhaps with no data
    await expect(page.locator('table')).toBeVisible();

    // 3. We should see no actual data rows since the backend failed
    const rowCount = await page.locator('table tbody tr').count();
    
    // Depending on frontend implementation, it might show 1 row saying "No data" or 0 rows
    // Let's assert the absence of a real data cell (like a company name)
    // If the frontend crashes completely on 422, this test will fail (which is good!)
    const hasData = await page.locator('td:has-text("Company")').isVisible();
    expect(hasData).toBe(false);
  });

  test('pagination limits should restrict displayed rows', async ({ page }) => {
    await page.goto(BASE_URL);

    // Wait for data load
    await expect(page.locator('table tbody tr').first()).toBeVisible();

    // The seeder injected 50 records.
    // By default, the limit should be 25 rows per page
    const rowCount = await page.locator('table tbody tr').count();
    
    // It should not exceed 25 rows on the first page
    expect(rowCount).toBeLessThanOrEqual(25);
    
    // Check pagination controls exist
    await expect(page.locator('text=Prev')).toBeVisible();
    await expect(page.locator('text=Next')).toBeVisible();
    
    // Verify that navigating to page 2 updates the URL
    await page.getByText('Next →').click();
    await expect(page).toHaveURL(/.*page=2.*/);
  });

});
