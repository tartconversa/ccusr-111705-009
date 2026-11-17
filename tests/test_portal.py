import unittest
from playwright.sync_api import sync_playwright
from test_browser import BrowserBaselineTest
from app.site import DATA

class PortalInteractionTest(BrowserBaselineTest):
    def test_browser_business_interaction(self):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            try:
                page = browser.new_page()
                page.goto(self.origin + "detail?id=" + DATA["items"][0]["id"], wait_until="domcontentloaded")
                page.locator('.marker').click();self.assertIn('store-01',page.locator('#store-popover').inner_text());page.locator('#pan').click();page.locator('.marker').click();page.locator('#brand').click();self.assertIn('store-02',page.locator('#store-popover').inner_text());self.assertEqual(page.locator('#brand-state').inner_text(),'试营业');page.locator('#zoom').click();self.assertEqual(page.locator('#viewport').get_attribute('data-complete'),'false')
            finally:
                browser.close()
