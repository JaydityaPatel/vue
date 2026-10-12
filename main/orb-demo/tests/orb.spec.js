import { test, expect } from '@playwright/test';

test('simulation animates varying bands without microphone access and fades to idle', async ({ page }) => {
  await page.addInitScript(() => {
    window.microphoneRequests = 0;
    navigator.mediaDevices.getUserMedia = async () => {
      window.microphoneRequests++;
      throw new DOMException('No microphone', 'NotAllowedError');
    };
  });
  await page.goto('/');
  await page.getByRole('button', { name: 'Simulate Audio' }).click();
  const stop = page.getByRole('button', { name: 'Stop Simulation' });
  await expect(stop).toHaveAttribute('aria-pressed', 'true');
  await expect(page.getByRole('status')).toContainText('Simulating audio');
  await expect.poll(() => page.evaluate(() => window.__orbDiagnostics.bands.level)).toBeGreaterThan(.2);
  const first = await page.evaluate(() => window.__orbDiagnostics.bands);
  await page.waitForTimeout(700);
  const second = await page.evaluate(() => window.__orbDiagnostics.bands);
  expect(Math.abs(first.mid - second.mid)).toBeGreaterThan(.01);
  expect(second.bass).toBeGreaterThan(.1);
  expect(second.high).toBeGreaterThan(.05);
  expect(await page.evaluate(() => window.microphoneRequests)).toBe(0);
  expect(await page.evaluate(() => window.__orbDiagnostics.contextState)).toBe('closed');
  await page.screenshot({ path: 'test-results/orb-simulation.png' });
  await stop.click();
  await expect(page.getByRole('status')).toContainText('Idle');
  await expect.poll(() => page.evaluate(() => window.__orbDiagnostics.bands.level)).toBeLessThan(.02);
  await page.getByRole('button', { name: 'Simulate Audio' }).click();
  await expect(page.getByRole('button', { name: 'Stop Simulation' })).toBeVisible();
});

test('switching between simulation and microphone releases the previous input', async ({ page, context }) => {
  await context.grantPermissions(['microphone']);
  await page.goto('/');
  await page.getByRole('button', { name: 'Start Audio' }).click();
  await expect(page.getByRole('button', { name: 'Stop Audio' })).toBeVisible();
  await page.getByRole('button', { name: 'Simulate Audio' }).click();
  await expect(page.getByRole('button', { name: 'Start Audio' })).toHaveAttribute('aria-pressed', 'false');
  expect(await page.evaluate(() => window.__orbDiagnostics.contextState)).toBe('closed');
  await expect(page.getByRole('button', { name: 'Stop Simulation' })).toBeVisible();
  await page.getByRole('button', { name: 'Start Audio' }).click();
  await expect(page.getByRole('button', { name: 'Stop Audio' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Simulate Audio' })).toHaveAttribute('aria-pressed', 'false');
  expect(await page.evaluate(() => window.__orbDiagnostics.simulating)).toBe(false);
});

test('renders animated WebGL particles and fits desktop and mobile', async ({ page }) => {
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto('/');
  await expect(page.getByRole('button', { name: 'Start Audio' })).toBeEnabled();
  await expect.poll(() => page.evaluate(() => window.__orbDiagnostics.frames)).toBeGreaterThan(12);
  expect(await page.evaluate(() => window.__orbDiagnostics.particles)).toBe(27648);
  await page.screenshot({ path: 'test-results/orb-desktop.png' });
  const before = await page.locator('canvas').screenshot();
  await page.waitForTimeout(450);
  const after = await page.locator('canvas').screenshot();
  expect(before.equals(after)).toBe(false);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: 'test-results/orb-mobile.png' });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  expect(errors).toEqual([]);
});

test('microphone drives FFT bands, smooths changes, and releases resources', async ({ page, context }) => {
  page.on('console', message => { if (message.type() === 'error') console.log(message.text()); });
  await page.addInitScript(() => {
    const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia = async (...args) => {
      try { return await original(...args); }
      catch (error) { console.error('getUserMedia:', error.name, error.message, error.stack); throw error; }
    };
  });
  await context.grantPermissions(['microphone']);
  await page.goto('/');
  await page.getByRole('button', { name: 'Start Audio' }).click();
  await expect(page.getByRole('button', { name: 'Stop Audio' })).toBeVisible();
  await expect.poll(() => page.evaluate(() => window.__orbDiagnostics.bands.level)).toBeGreaterThan(.3);
  const bands = await page.evaluate(() => window.__orbDiagnostics.bands);
  expect(bands.bass).toBeGreaterThan(.05);
  expect(bands.mid).toBeGreaterThan(.02);
  expect(bands.high).toBeGreaterThan(.01);
  await page.screenshot({ path: 'test-results/orb-listening.png' });
  await page.getByRole('button', { name: 'Stop Audio' }).click();
  await expect(page.getByRole('status')).toContainText('microphone off');
  expect(await page.evaluate(() => window.__orbDiagnostics.contextState)).toBe('closed');
  await expect.poll(() => page.evaluate(() => window.__orbDiagnostics.bands.level)).toBeLessThan(.02);
  await page.getByRole('button', { name: 'Start Audio' }).click();
  await expect(page.getByRole('button', { name: 'Stop Audio' })).toBeVisible();
});

test('denied microphone permission leaves the idle orb usable', async ({ page }) => {
  await page.addInitScript(() => {
    navigator.mediaDevices.getUserMedia = async () => { throw new DOMException('Denied', 'NotAllowedError'); };
  });
  await page.goto('/');
  await page.getByRole('button', { name: 'Start Audio' }).click();
  await expect(page.getByRole('status')).toContainText('permission denied');
  await expect(page.getByRole('button', { name: 'Start Audio' })).toBeEnabled();
  expect(await page.evaluate(() => window.__orbDiagnostics.contextState)).toBe('closed');
  await expect.poll(() => page.evaluate(() => window.__orbDiagnostics.frames)).toBeGreaterThan(10);
});

test('FFT separates frequencies and uses gradual attack and release', async ({ page }) => {
  await page.goto('/');
  const result = await page.evaluate(async () => {
    const { AudioInput } = await import('/utils/audio.js');
    const input = new AudioInput();
    const context = new AudioContext();
    await context.resume();
    input.context = context;
    input.analyser = context.createAnalyser();
    input.analyser.fftSize = 2048;
    input.analyser.smoothingTimeConstant = 0;
    input.frequency = new Uint8Array(input.analyser.frequencyBinCount);
    input.waveform = new Float32Array(input.analyser.fftSize);
    const oscillator = context.createOscillator();
    const gain = context.createGain();
    gain.gain.value = .2;
    oscillator.connect(gain).connect(input.analyser);
    oscillator.start();
    const measurements = [];
    for (const frequency of [90, 1000, 6500]) {
      oscillator.frequency.value = frequency;
      await new Promise(resolve => setTimeout(resolve, 200));
      for (let i = 0; i < 80; i++) input.sample(1/60);
      measurements.push({ ...input.bands });
    }
    const before = input.bands.level;
    gain.gain.value = 0;
    await new Promise(resolve => setTimeout(resolve, 150));
    input.sample(1/60);
    const first = input.bands.level;
    for (let i = 0; i < 120; i++) input.sample(1/60);
    const settled = input.bands.level;
    oscillator.stop();
    gain.disconnect();
    await input.stop();
    return { measurements, before, first, settled };
  });
  const [bass, mid, high] = result.measurements;
  expect(bass.bass).toBeGreaterThan(bass.mid * 3);
  expect(mid.mid).toBeGreaterThan(mid.bass * 3);
  expect(high.high).toBeGreaterThan(high.mid * 3);
  expect(result.first).toBeLessThan(result.before);
  expect(result.first).toBeGreaterThan(result.before * .8);
  expect(result.settled).toBeLessThan(.01);
});
