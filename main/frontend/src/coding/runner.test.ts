import { afterEach, describe, expect, it, vi } from 'vitest';
import { executeCases } from './runner';

class FakeWorker {
  onmessage: ((event: MessageEvent) => void) | null = null;
  onerror: ((event: ErrorEvent) => void) | null = null;
  terminate = vi.fn();
  postMessage = vi.fn();
}

describe('Pyodide worker runner', () => {
  afterEach(() => { vi.useRealTimers(); vi.restoreAllMocks(); });

  it('returns per-case pass/fail/error states from the worker', async () => {
    const worker = new FakeWorker();
    vi.stubGlobal('Worker', vi.fn(() => worker));
    const promise = executeCases('class Solution: pass', [{ input: [1], expected: 1 }]);
    worker.onmessage?.({ data: { results: [{ index: 0, status: 'failed', actual: 2, expected: 1 }] } } as MessageEvent);
    await expect(promise).resolves.toEqual([{ index: 0, status: 'failed', actual: 2, expected: 1 }]);
    expect(worker.terminate).toHaveBeenCalledOnce();
  });

  it('kills a worker that exceeds its time limit', async () => {
    vi.useFakeTimers();
    const worker = new FakeWorker();
    vi.stubGlobal('Worker', vi.fn(() => worker));
    const promise = executeCases('while True: pass', [{ input: [], expected: null }], 20);
    await vi.advanceTimersByTimeAsync(5021);
    await expect(promise).resolves.toEqual([{ index: 0, status: 'timeout', expected: null }]);
    expect(worker.terminate).toHaveBeenCalledOnce();
  });
});
