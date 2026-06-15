import { chromium } from '@playwright/test';

async function debugPage() {
  const browser = await chromium.launch({ headless: false });
  const context = await browser.newContext({
    extraHTTPHeaders: {
      'Authorization': 'Bearer dev-engineer-token'
    }
  });
  const page = await context.newPage();

  console.log('Navigating to onboarding page...');
  await page.goto('http://localhost:5173/onboarding', {
    waitUntil: 'networkidle',
    timeout: 10000
  });

  console.log('Waiting for page to be ready...');
  await page.waitForTimeout(3000);

  console.log('\n=== Page HTML ===');
  const html = await page.content();
  console.log(html.substring(0, 2000));

  console.log('\n=== Looking for buttons ===');
  const buttons = await page.locator('button').all();
  console.log(`Found ${buttons.length} buttons`);

  for (let i = 0; i < Math.min(buttons.length, 10); i++) {
    const text = await buttons[i].textContent();
    const testId = await buttons[i].getAttribute('data-testid');
    const classes = await buttons[i].getAttribute('class');
    console.log(`Button ${i + 1}:`);
    console.log(`  Text: "${text}"`);
    console.log(`  data-testid: ${testId}`);
    console.log(`  Classes: ${classes?.substring(0, 80)}`);
  }

  console.log('\n=== Taking screenshot ===');
  await page.screenshot({ path: 'onboarding-debug.png', fullPage: true });
  console.log('Screenshot saved to onboarding-debug.png');

  console.log('\nPress Ctrl+C to exit (browser will stay open for manual inspection)');
  await page.waitForTimeout(300000); // 5 minutes

  await browser.close();
}

debugPage().catch(console.error);
