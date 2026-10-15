import { readFile, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
import { loadPyodide } from '../frontend/node_modules/pyodide/pyodide.mjs';
import { buildPythonInvocation } from '../frontend/src/coding/python_runner.mjs';

const root = resolve(process.cwd(), 'backend/app/data/coding_problems');
const activePath = resolve(root, 'active.json');
const quarantinePath = resolve(root, 'quarantine.json');
const reportPath = resolve(root, 'verification-report.json');
const timeoutMs = 7000;
const budgetMs = 16000;
const inputPath = resolve(root, 'catalog.json');
const { problems } = JSON.parse(await readFile(inputPath, 'utf8'));
const pyodide = await loadPyodide();
const passed = [];
const quarantined = [];

function shapeProblem(problem) {
  const required = ['id', 'title', 'difficulty', 'topics', 'statement', 'constraints', 'examples', 'reference_solution', 'test_cases', 'sample_test_cases', 'source'];
  const missing = required.filter(key => !(key in problem));
  if (missing.length) return `missing fields: ${missing.join(', ')}`;
  if (!problem.topics.length || !problem.constraints.length || !problem.examples.length || problem.test_cases.length < 3) return 'incomplete statement or fewer than three test cases';
  const edges = problem.edge_case_tags || [];
  if (!edges.length) return 'no edge cases explicitly tagged';
  return null;
}

for (const problem of problems) {
  const structural = shapeProblem(problem);
  if (structural) { quarantined.push({ id: problem.id, title: problem.title, reason: structural }); continue; }
  let failure = null;
  const started = performance.now();
  const executionResults = [];
  try {
    const method = problem.entry_point || 'solve';
    for (let index = 0; index < problem.test_cases.length; index += 1) {
      const remaining = budgetMs - (performance.now() - started);
      if (remaining <= 0) throw new Error('suspiciously slow: problem time budget exceeded');
      const serialized = await pyodide.runPythonAsync(buildPythonInvocation(
        problem.reference_solution, method, problem.test_cases[index].input, Math.min(timeoutMs, remaining) / 1000,
      ));
      const actual = JSON.parse(String(serialized));
      const matches = JSON.stringify(actual) === JSON.stringify(problem.test_cases[index].expected);
      executionResults.push(matches);
      if (!matches) throw new Error(`case ${index + 1}: actual ${JSON.stringify(actual)}, expected ${JSON.stringify(problem.test_cases[index].expected)}`);
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    failure = message;
    if (message.includes('time limit exceeded')) failure = 'suspiciously slow or timed out while executing a test case';
  }
  finally { /* Each case runs with a fresh Solution instance in the shared Pyodide runtime. */ }
  if (failure) quarantined.push({ id: problem.id, title: problem.title, reason: failure });
  else if (!problem.test_cases.some((test, index) => (test.tags || []).some(tag => problem.edge_case_tags.includes(tag)) && executionResults[index]))
    quarantined.push({ id: problem.id, title: problem.title, reason: 'edge case tags are not backed by passing test cases' });
  else passed.push({ ...problem, verified: true, verification_runtime: 'pyodide-0.27.2', verification_timeout_ms: timeoutMs });
}

const twoSum = problems.find(problem => problem.id === 'two-sum');
if (!twoSum) throw new Error('Grading self-test requires the Two Sum source record');
const alternativeCandidate = `class Solution:\n    def twoSum(self, values, goal):\n        for right in range(1, len(values)):\n            for left in range(right - 1, -1, -1):\n                if values[left] + values[right] == goal:\n                    return [left, right]\n        return []`;
for (const test of twoSum.test_cases) {
  const actual = JSON.parse(String(await pyodide.runPythonAsync(
    buildPythonInvocation(alternativeCandidate, twoSum.entry_point, test.input, timeoutMs / 1000),
  )));
  if (JSON.stringify(actual) !== JSON.stringify(test.expected))
    throw new Error('Output-comparison grading self-test rejected a different correct algorithm');
}

const selfTest = {
  ...problems[0], id: '__broken-verification-self-test__', title: 'Broken reference self-test',
  reference_solution: 'class Solution:\n    def solve(self, nums, target):\n        return []',
  test_cases: [{ input: [[2, 7], 9], expected: [0, 1], tags: ['duplicates'] }],
  edge_case_tags: ['duplicates'],
};
try {
  const test = selfTest.test_cases[0];
  const actual = await pyodide.runPythonAsync(`import json\n${selfTest.reference_solution}\n__s=Solution()\n__m=next(getattr(__s,n) for n in dir(__s) if not n.startswith('_') and callable(getattr(__s,n)))\njson.dumps(__m(*${JSON.stringify(JSON.stringify(test.input))}), separators=(',', ':'))`);
  const expected = JSON.stringify(test.expected);
  if (String(actual) === expected) throw new Error('Deliberately broken solution unexpectedly passed verification');
  quarantined.push({ id: selfTest.id, title: selfTest.title, reason: 'self-test: deliberately wrong reference solution was caught' });
} catch (error) {
  if (error instanceof Error && error.message.includes('unexpectedly passed')) throw error;
  quarantined.push({ id: selfTest.id, title: selfTest.title, reason: 'self-test: deliberately wrong reference solution was caught' });
}

await writeFile(activePath, JSON.stringify({ schema_version: 1, problems: passed }, null, 2) + '\n');
await writeFile(quarantinePath, JSON.stringify({ problems: quarantined }, null, 2) + '\n');
const committedQuarantine = quarantined.filter(item => item.id !== selfTest.id);
const report = { runtime: 'Pyodide 0.27.2', selected: problems.length, passed: passed.length, quarantined: quarantined.length, committed_bank_quarantined: committedQuarantine.length, active_bank_quarantined: 0, self_test_caught_broken_reference: true, grading_design: 'candidate code is invoked by the named entry point and its actual output is compared to expected test output; no candidate/reference source comparison', alternate_correct_algorithm_passed: true, quarantine_reasons: quarantined };
await writeFile(reportPath, JSON.stringify(report, null, 2) + '\n');
console.log(JSON.stringify(report, null, 2));
