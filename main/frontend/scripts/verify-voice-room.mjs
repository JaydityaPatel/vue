// Real WebGL layout smoke check with fixture HTTP data. No live LLM or audio claims.
// Reuses the orb demo's existing Playwright installation.
import { createRequire } from 'node:module';
import { mkdirSync } from 'node:fs';
import assert from 'node:assert/strict';
const require = createRequire(new URL('../../orb-demo/package.json', import.meta.url));
const { chromium } = require('@playwright/test');
const baseURL = process.env.VOICE_TEST_URL || 'http://127.0.0.1:5175';
const browser = await chromium.launch({ headless: true, args: [
  '--enable-unsafe-swiftshader', '--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream',
] });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  const errors = [];
  const requests = [];
  page.on('pageerror', error => errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') errors.push(message.text()); });
  page.on('request', request => requests.push(request.url()));
  await page.addInitScript(() => localStorage.setItem('vue_access_token', 'fixture-only-token'));
  await page.route('**/auth/me', route => route.fulfill({ json: { id: 'fixture', email: 'fixture@example.com', full_name: 'Test Candidate' } }));
  await page.route('**/interviews/fixture', route => route.fulfill({ json: {
    session_id: 'fixture', status: 'in_progress', started_at: '', completed_at: null,
    time_remaining: 1800, current_topic: 'Systems', turns_on_current_topic: 0,
    topic_coverage: { Systems: 'in_progress' }, completion_reason: null, report_generation: null,
    config: { role: 'Software engineer', duration: 30 },
    turns: [
      { id: 't1', turn_index: 0, question_text: 'Tell me about a project you are proud of.', answer_text: 'I built a real-time data pipeline. We measured throughput and tested out-of-order events.' },
      { id: 't2', turn_index: 1, question_text: 'Which tradeoffs did you make, and how did you validate them?', answer_text: null },
    ],
  } }));
  await page.goto(`${baseURL}/dashboard`);
  await page.getByRole('heading', { name: /good|practice|dashboard|welcome/i }).first().waitFor();
  assert(!requests.some(url => /components\/Orb|InterviewRoomPage/.test(url)), 'Orb code loaded on Dashboard');
  await page.goto(`${baseURL}/interview/fixture`);
  await page.getByText('Which tradeoffs did you make, and how did you validate them?').waitFor();
  await page.locator('.voice-orb canvas').waitFor();
  await page.waitForTimeout(1200);
  mkdirSync('test-results/phase5', { recursive: true });
  const desktop = await page.locator('.voice-grid').boundingBox();
  const orb = await page.locator('.voice-orb').boundingBox();
  const transcript = await page.getByRole('complementary', { name: 'Conversation' }).boundingBox();
  assert(orb.width > 100 && Math.abs(orb.width - orb.height) < 2, 'Orb canvas is not square');
  assert(transcript.x > orb.x + orb.width, 'Desktop layout is not split');
  await page.screenshot({ path: 'test-results/phase5/room-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.waitForTimeout(300);
  const mobileOrb = await page.locator('.voice-orb').boundingBox();
  const mobileTranscript = await page.getByRole('complementary', { name: 'Conversation' }).boundingBox();
  assert(mobileTranscript.y > mobileOrb.y + mobileOrb.height, 'Mobile layout is not stacked');
  assert(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'Horizontal overflow');
  await page.screenshot({ path: 'test-results/phase5/room-mobile.png', fullPage: true });
  // Exercise the real browser AudioContext/worklet using Chromium's synthetic mic.
  const capture = await page.evaluate(async () => {
    const { Microphone } = await import('/src/voice/microphone.ts');
    const mic = new Microphone();
    const frames = [];
    let peak = 0;
    try {
      await mic.open(frame => frames.push(frame), level => { peak = Math.max(peak, level); });
      mic.enable(true);
      await new Promise(resolve => setTimeout(resolve, 1500));
      mic.enable(false);
      const before = frames.length;
      await new Promise(resolve => setTimeout(resolve, 150));
      return { frames: before, correctlySized: frames.every(frame => frame.byteLength === 1024),
        muted: frames.length === before, measuredLevel: peak > 0 };
    } finally { mic.dispose(); }
  });
  assert(capture.frames >= 3 && capture.correctlySized && capture.muted && capture.measuredLevel, 'Browser PCM capture failed');
  assert.deepEqual(errors, [], 'Browser/WebGL errors');
  console.log(JSON.stringify({ dashboardLazyLoad: true, desktopSplit: true, mobileStack: true, desktopWidth: desktop.width, webglErrors: errors.length, syntheticMic: capture }));
} finally { await browser.close(); }
