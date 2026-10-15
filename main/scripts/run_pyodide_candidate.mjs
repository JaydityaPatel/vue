import { readFile } from 'node:fs/promises';
import { loadPyodide } from '../frontend/node_modules/pyodide/pyodide.mjs';
import { buildPythonInvocation } from '../frontend/src/coding/python_runner.mjs';

const payload = JSON.parse(await readFile(process.argv[2], 'utf8'));
const pyodide = await loadPyodide();
const results = [];
for (const test of payload.test_cases) {
  try {
    const serialized = await pyodide.runPythonAsync(buildPythonInvocation(
      payload.code, payload.entry_point, test.input, 7,
    ));
    const actual = JSON.parse(String(serialized));
    results.push({ status: JSON.stringify(actual) === JSON.stringify(test.expected) ? 'passed' : 'failed',
      actual, expected: test.expected });
  } catch (error) {
    results.push({ status: 'error', expected: test.expected, error: String(error) });
  }
}
process.stdout.write(JSON.stringify(results));
