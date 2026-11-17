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
                page.locator('#pan').click();self.assertEqual(page.locator('#viewport').get_attribute('data-region'),'东区');self.assertEqual(page.locator('.marker').get_attribute('data-store'),'store-02')
            finally:
                browser.close()
