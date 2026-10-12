import { defineConfig } from '@playwright/test';
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';

// A real PCM stream fed through Chromium's microphone device and Web Audio FFT.
mkdirSync('.cache', { recursive: true });
const sampleRate = 48000;
const count = sampleRate * 4;
const wav = Buffer.alloc(44 + count * 2);
wav.write('RIFF', 0); wav.writeUInt32LE(wav.length - 8, 4); wav.write('WAVEfmt ', 8);
wav.writeUInt32LE(16, 16); wav.writeUInt16LE(1, 20); wav.writeUInt16LE(1, 22);
wav.writeUInt32LE(sampleRate, 24); wav.writeUInt32LE(sampleRate * 2, 28);
wav.writeUInt16LE(2, 32); wav.writeUInt16LE(16, 34); wav.write('data', 36);
wav.writeUInt32LE(count * 2, 40);
for (let i = 0; i < count; i++) {
  const t = i / sampleRate;
  const signal = .16 * (Math.sin(2*Math.PI*90*t) + Math.sin(2*Math.PI*1000*t) + Math.sin(2*Math.PI*6500*t));
  wav.writeInt16LE(Math.round(signal * 32767), 44 + i * 2);
}
writeFileSync('.cache/microphone.wav', wav);

export default defineConfig({
  testDir: './tests',
  fullyParallel: false,
  workers: 1,
  use: {
    channel: 'chromium',
    baseURL: 'http://127.0.0.1:5174',
    viewport: { width: 1100, height: 900 },
    launchOptions: {
      args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream', `--use-file-for-fake-audio-capture=${path.resolve('.cache/microphone.wav').replaceAll('\\', '/')}`, '--enable-unsafe-swiftshader'],
    },
  },
  webServer: { command: 'node server.mjs', url: 'http://127.0.0.1:5174', reuseExistingServer: !process.env.CI },
});
