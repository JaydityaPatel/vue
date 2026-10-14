import { afterEach, expect, it, vi } from 'vitest';
import { startOrbLoop } from './loop';

afterEach(() => vi.restoreAllMocks());
it.each([false, true])('caps drawing with STT=%s and stops when hidden/unmounted', stt => {
  let tick!: FrameRequestCallback;
  vi.spyOn(window, 'requestAnimationFrame').mockImplementation(callback => { tick = callback; return 123; });
  const cancel = vi.spyOn(window, 'cancelAnimationFrame').mockImplementation(() => {});
  const hidden = vi.spyOn(document, 'hidden', 'get').mockReturnValue(false);
  const draw = vi.fn();
  const dispose = startOrbLoop(draw, stt);
  for (let t = 0; t <= 1000; t += 1) tick(t);
  expect(draw.mock.calls.length).toBeLessThanOrEqual(stt ? 10 : 30);
  expect(draw.mock.calls.length).toBeGreaterThanOrEqual(stt ? 9 : 29);
  draw.mockClear(); hidden.mockReturnValue(true);
  for (let t = 1001; t <= 2000; t++) tick(t);
  expect(draw).not.toHaveBeenCalled();
  dispose(); expect(cancel).toHaveBeenCalledWith(123);
});
