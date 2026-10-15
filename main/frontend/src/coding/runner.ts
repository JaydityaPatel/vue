export type CaseStatus = 'passed' | 'failed' | 'error' | 'timeout';
export interface CodingCase { input: unknown[]; expected: unknown }
export interface CaseResult { index: number; status: CaseStatus; actual?: unknown; expected: unknown; error?: string }

export async function executeCases(code: string, cases: CodingCase[], timeoutMs = 7000, methodName = 'twoSum'): Promise<CaseResult[]> {
  if (typeof Worker === 'undefined') throw new Error('Web Workers are unavailable in this browser.');
  const worker = new Worker(new URL('./worker.ts', import.meta.url), { type: 'module' });
  return new Promise((resolve, reject) => {
    let settled = false;
    const timer = setTimeout(() => {
      if (!settled) { settled = true; worker.terminate(); resolve(cases.map((test, index) => ({ index, status: 'timeout', expected: test.expected }))); }
    }, timeoutMs + 5000);
    worker.onmessage = event => {
      if (settled) return;
      settled = true; clearTimeout(timer); worker.terminate();
      if (event.data.error) reject(new Error(String(event.data.error)));
      else resolve(event.data.results as CaseResult[]);
    };
    worker.onerror = event => {
      if (settled) return;
      settled = true; clearTimeout(timer); worker.terminate(); reject(new Error(event.message || 'Pyodide worker failed'));
    };
    worker.postMessage({ code, cases, timeoutMs, methodName });
  });
}
