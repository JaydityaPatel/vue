import { readFileSync } from 'node:fs';
import { runInNewContext } from 'node:vm';
import { expect, it } from 'vitest';

interface Processor {
  port: { onmessage: (event: { data: { enabled: boolean } }) => void };
  process: (inputs: Float32Array[][]) => boolean;
}
it.each([16000, 44100, 48000])('resamples %i Hz PCM to mono 16 kHz and gates muted frames', sampleRate => {
  const frames: ArrayBuffer[] = [];
  let ProcessorClass!: new () => Processor;
  runInNewContext(readFileSync('public/audio/pcm-worklet.js', 'utf8'), {
    sampleRate,
    AudioWorkletProcessor: class { port = { postMessage: (frame: ArrayBuffer) => frames.push(frame) }; },
    registerProcessor: (_name: string, ctor: new () => Processor) => { ProcessorClass = ctor; },
  });
  const processor = new ProcessorClass();
  processor.process([[new Float32Array(1024).fill(.5)]]);
  expect(frames).toHaveLength(0);
  processor.port.onmessage({ data: { enabled: true } });
  for (let i = 0; i < sampleRate; i += 128) {
    const frame = new Float32Array(Math.min(128, sampleRate - i)).fill(.5);
    processor.process([[frame, frame]]);
  }
  expect(frames).toHaveLength(31); // 15872 samples + 128 retained for the next frame.
  for (const frame of frames) {
    expect(frame.byteLength).toBe(1024);
    expect(new DataView(frame).getInt16(0, true)).toBe(16384);
  }
  processor.port.onmessage({ data: { enabled: false } });
  processor.process([[new Float32Array(1024).fill(1)]]);
  expect(frames).toHaveLength(31);
});
