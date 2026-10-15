/// <reference lib="webworker" />
import type { CodingCase, CaseResult } from './runner';
import { buildPythonInvocation } from './python_runner.mjs';

declare const self: DedicatedWorkerGlobalScope;
interface PyodideRuntime { runPythonAsync(source: string): Promise<unknown>; runPython(source: string): unknown; globals: { set(key: string, value: unknown): void } }
interface PyodideLoader { loadPyodide(options: { indexURL: string; interruptBuffer?: Int32Array }): Promise<PyodideRuntime> }
let pyodidePromise: Promise<PyodideRuntime> | undefined;
let interruptBuffer: Int32Array | undefined;
const MAX_RESULT_BYTES = 64_000;

self.onmessage = async event => {
  const { code, cases, timeoutMs, methodName } = event.data as { code: string; cases: CodingCase[]; timeoutMs: number; methodName: string };
  const results: CaseResult[] = [];
  let pyodide: PyodideRuntime;
  try {
    if (!pyodidePromise) {
      if (typeof SharedArrayBuffer !== 'undefined') interruptBuffer = new Int32Array(new SharedArrayBuffer(4));
      const loaderUrl = new URL('/pyodide/pyodide.mjs', self.location.origin);
      const runtime = await import(/* @vite-ignore */ loaderUrl.href) as PyodideLoader;
      pyodidePromise = runtime.loadPyodide({ indexURL: new URL('/pyodide/', self.location.origin).href, interruptBuffer });
    }
    pyodide = await pyodidePromise;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    self.postMessage({ results: cases.map((test, index) => ({ index, status: 'error', expected: test.expected, error: message })) });
    return;
  }
  try {
    const deadline = Date.now() + timeoutMs;
    const watchdog = setInterval(() => {
      if (Date.now() > deadline && interruptBuffer) Atomics.store(interruptBuffer, 0, 2);
    }, 20);
    for (let index = 0; index < cases.length; index += 1) {
      const test = cases[index];
      try {
        const remainingMs = Math.max(1, deadline - Date.now());
        const result = await Promise.race([
          pyodide.runPythonAsync(buildPythonInvocation(code, methodName, test.input)),
          new Promise<never>((_, reject) => setTimeout(() => reject(new Error('TIME_LIMIT_EXCEEDED')), remainingMs)),
        ]);
        pyodide.runPython('del __vue_fn, __vue_obj, __vue_result');
        const actual: unknown = JSON.parse(String(result));
        const expectedSerialized = JSON.stringify(test.expected);
        const actualSerialized = JSON.stringify(actual);
        if (actualSerialized.length > MAX_RESULT_BYTES) throw new Error('Result exceeded the output size limit.');
        results.push({ index, status: actualSerialized === expectedSerialized ? 'passed' : 'failed', actual, expected: test.expected });
      } catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        results.push({ index, status: message.includes('TIME_LIMIT_EXCEEDED') ? 'timeout' : 'error', expected: test.expected, error: message });
        if (message.includes('TIME_LIMIT_EXCEEDED')) break;
      }
    }
    clearInterval(watchdog);
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    self.postMessage({ error: message });
    return;
  }
  self.postMessage({ results });
};
