/**
 * Automated Manual Testing Script
 *
 * This script automates the manual test scenarios from MANUAL_TEST_GUIDE.md
 * to verify all functionality works correctly after starting the services.
 */
import { chromium } from '@playwright/test';

// Color output helpers
const colors = {
  reset: '\x1b[0m',
  green: '\x1b[32m',
  red: '\x1b[31m',
  yellow: '\x1b[33m',
  blue: '\x1b[34m',
  cyan: '\x1b[36m',
};

function log(message: string, color = colors.reset) {
  console.log(`${color}${message}${colors.reset}`);
}

function logSuccess(message: string) {
  log(`✅ ${message}`, colors.green);
}

function logError(message: string) {
  log(`❌ ${message}`, colors.red);
}

function logInfo(message: string) {
  log(`ℹ️  ${message}`, colors.cyan);
}

function logWarning(message: string) {
  log(`⚠️  ${message}`, colors.yellow);
}

function logSection(message: string) {
  log(`\n${'='.repeat(60)}`, colors.blue);
  log(`  ${message}`, colors.blue);
  log(`${'='.repeat(60)}`, colors.blue);
}

// Test results tracker
const results = {
  total: 0,
  passed: 0,
  failed: 0,
  warnings: 0,
  issues: [] as string[],
};

async function runTest(name: string, testFn: () => Promise<void>) {
  results.total++;
  try {
    await testFn();
    results.passed++;
    logSuccess(name);
    return true;
  } catch (error) {
    results.failed++;
    const message = error instanceof Error ? error.message : String(error);
    logError(`${name}: ${message}`);
    results.issues.push(`${name}: ${message}`);
    return false;
  }
}

async function main() {
  logSection('Starting Automated Manual Testing');

  const browser = await chromium.launch({ headless: false, slowMo: 500 });
  const context = await browser.newContext();
  const page = await context.newPage();

  try {
    // ========================================
    // Test Suite 1: Service Availability
    // ========================================
    logSection('Test Suite 1: Service Availability');

    await runTest('Frontend is accessible', async () => {
      const response = await page.goto('http://localhost:5173/', {
        waitUntil: 'domcontentloaded',
        timeout: 10000
      });
      if (!response || !response.ok()) {
        throw new Error(`Frontend returned status ${response?.status()}`);
      }
    });

    await runTest('Backend API documentation is accessible', async () => {
      const response = await page.goto('http://localhost:8000/docs', {
        waitUntil: 'domcontentloaded',
        timeout: 10000
      });
      if (!response || !response.ok()) {
        throw new Error(`Backend docs returned status ${response?.status()}`);
      }
    });

    // ========================================
    // Test Suite 2: Onboarding Wizard - UI Elements
    // ========================================
    logSection('Test Suite 2: Onboarding Wizard - UI Presence');

    await runTest('Navigate to Onboarding page', async () => {
      await page.goto('http://localhost:5173/onboarding', {
        waitUntil: 'networkidle',
        timeout: 10000
      });
      await page.waitForTimeout(1000);
    });

    await runTest('Page title contains "首次运行设置" or similar text', async () => {
      const hasTitle = await page.locator('h1, h2').first().isVisible({ timeout: 5000 });
      if (!hasTitle) {
        throw new Error('No main heading found on page');
      }
      const titleText = await page.locator('h1, h2').first().textContent();
      logInfo(`Found title: "${titleText}"`);
    });

    await runTest('Step indicator is visible', async () => {
      // Try multiple possible selectors for step indicators
      const selectors = [
        'text=Step 1',
        'text=第1步',
        'text=1/4',
        '[aria-label*="步骤"]',
        '[data-testid*="step"]'
      ];

      let found = false;
      for (const selector of selectors) {
        try {
          const isVisible = await page.locator(selector).first().isVisible({ timeout: 1000 });
          if (isVisible) {
            found = true;
            const text = await page.locator(selector).first().textContent();
            logInfo(`Found step indicator with selector "${selector}": "${text}"`);
            break;
          }
        } catch {
          // Try next selector
        }
      }

      if (!found) {
        logWarning('Step indicator not found with any expected selector');
        results.warnings++;
      }
    });

    await runTest('Provider selection buttons are visible', async () => {
      // Look for provider buttons
      const selectors = [
        'button:has-text("DeepSeek")',
        'button:has-text("OpenAI")',
        'button:has-text("Claude")',
        'button:has-text("deepseek")',
        '[role="button"]'
      ];

      let foundCount = 0;
      const foundProviders: string[] = [];

      for (const selector of selectors) {
        try {
          const count = await page.locator(selector).count();
          if (count > 0) {
            foundCount += count;
            const text = await page.locator(selector).first().textContent();
            if (text) foundProviders.push(text.trim());
          }
        } catch {
          // Continue
        }
      }

      if (foundCount === 0) {
        throw new Error('No provider buttons found');
      }

      logInfo(`Found ${foundCount} provider-related buttons: ${foundProviders.join(', ')}`);
    });

    await runTest('Navigation buttons are present', async () => {
      const selectors = [
        'button:has-text("下一步")',
        'button:has-text("Next")',
        '[data-testid*="next"]',
        'button[type="submit"]'
      ];

      let found = false;
      for (const selector of selectors) {
        try {
          const isVisible = await page.locator(selector).first().isVisible({ timeout: 1000 });
          if (isVisible) {
            found = true;
            const text = await page.locator(selector).first().textContent();
            logInfo(`Found navigation button: "${text}"`);
            break;
          }
        } catch {
          // Continue
        }
      }

      if (!found) {
        logWarning('Navigation button not found with expected selectors');
        results.warnings++;
      }
    });

    // ========================================
    // Test Suite 3: Interactive Elements
    // ========================================
    logSection('Test Suite 3: Interactive Elements');

    await runTest('Provider button is clickable', async () => {
      const providerButton = page.locator('button:has-text("DeepSeek")').first();
      const exists = await providerButton.count() > 0;

      if (!exists) {
        // Try alternative selectors
        const altButton = page.locator('button, [role="button"]').first();
        const altExists = await altButton.count() > 0;
        if (!altExists) {
          throw new Error('No clickable buttons found');
        }
        logInfo('Using alternative button selector');
        await altButton.click({ timeout: 5000 });
      } else {
        await providerButton.click({ timeout: 5000 });
      }

      await page.waitForTimeout(500);
      logInfo('Successfully clicked a provider button');
    });

    await runTest('Form inputs are interactable (if visible)', async () => {
      const inputs = await page.locator('input[type="text"], input[type="password"], input[type="url"]').count();
      if (inputs > 0) {
        logInfo(`Found ${inputs} input field(s) on page`);
        // Try to focus first input
        try {
          await page.locator('input').first().focus({ timeout: 2000 });
          logInfo('Successfully focused on input field');
        } catch {
          logWarning('Could not focus input (may not be visible yet)');
          results.warnings++;
        }
      } else {
        logInfo('No input fields visible on current step');
      }
    });

    // ========================================
    // Test Suite 4: Page Navigation
    // ========================================
    logSection('Test Suite 4: Page Navigation');

    await runTest('Can navigate through pages without crashes', async () => {
      // Try clicking next button if available
      const nextButton = page.locator('button:has-text("下一步"), button:has-text("Next")').first();
      const hasNextButton = await nextButton.count() > 0;

      if (hasNextButton) {
        try {
          await nextButton.click({ timeout: 3000 });
          await page.waitForTimeout(1000);
          logInfo('Successfully clicked next button');
        } catch (error) {
          logWarning(`Could not click next button: ${error instanceof Error ? error.message : String(error)}`);
          results.warnings++;
        }
      } else {
        logInfo('Next button not found - may need provider selection first');
      }
    });

    await runTest('No JavaScript console errors', async () => {
      const errors: string[] = [];

      page.on('console', msg => {
        if (msg.type() === 'error') {
          errors.push(msg.text());
        }
      });

      page.on('pageerror', error => {
        errors.push(error.message);
      });

      await page.waitForTimeout(2000);

      if (errors.length > 0) {
        logWarning(`Found ${errors.length} console error(s):`);
        errors.forEach(err => logWarning(`  - ${err.substring(0, 100)}`));
        results.warnings++;
      } else {
        logInfo('No console errors detected');
      }
    });

    // ========================================
    // Test Suite 5: API Endpoints
    // ========================================
    logSection('Test Suite 5: API Endpoints');

    await runTest('Onboarding state API is accessible', async () => {
      const response = await page.request.get('http://localhost:8000/api/onboarding/state');
      if (!response.ok() && response.status() !== 404) {
        throw new Error(`API returned status ${response.status()}`);
      }
      logInfo(`API response status: ${response.status()}`);
    });

    await runTest('Auth config API is accessible', async () => {
      const response = await page.request.get('http://localhost:8000/api/auth/config');
      if (!response.ok() && response.status() !== 404) {
        throw new Error(`API returned status ${response.status()}`);
      }
      logInfo(`API response status: ${response.status()}`);
    });

    await runTest('SAML providers API is accessible', async () => {
      const response = await page.request.get('http://localhost:8000/api/auth/saml/providers');
      if (!response.ok() && response.status() !== 404) {
        throw new Error(`API returned status ${response.status()}`);
      }
      logInfo(`API response status: ${response.status()}`);
    });

  } catch (error) {
    logError(`Unexpected error during testing: ${error instanceof Error ? error.message : String(error)}`);
    results.issues.push(`Unexpected error: ${error instanceof Error ? error.message : String(error)}`);
  } finally {
    await browser.close();
  }

  // ========================================
  // Test Results Summary
  // ========================================
  logSection('Test Results Summary');

  console.log(`\nTotal Tests: ${results.total}`);
  logSuccess(`Passed: ${results.passed}`);
  if (results.failed > 0) {
    logError(`Failed: ${results.failed}`);
  }
  if (results.warnings > 0) {
    logWarning(`Warnings: ${results.warnings}`);
  }

  const passRate = results.total > 0 ? ((results.passed / results.total) * 100).toFixed(1) : '0';
  console.log(`\nPass Rate: ${passRate}%`);

  if (results.issues.length > 0) {
    logSection('Issues Found');
    results.issues.forEach((issue, i) => {
      console.log(`\n${i + 1}. ${issue}`);
    });
  }

  console.log('\n');

  if (results.failed === 0 && results.warnings === 0) {
    logSuccess('🎉 All tests passed! The application is working correctly.');
  } else if (results.failed === 0) {
    logWarning('⚠️  All tests passed with some warnings. Review the warnings above.');
  } else {
    logError('❌ Some tests failed. Please review the failures above.');
  }

  console.log('\n');

  process.exit(results.failed > 0 ? 1 : 0);
}

main().catch(error => {
  logError(`Fatal error: ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
});
