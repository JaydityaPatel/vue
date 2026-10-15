import Editor from '@monaco-editor/react';
import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { api } from '../api/client';
import { executeCases, type CaseResult, type CodingCase } from '../coding/runner';
import { apiErrorMessage } from '../utils/errors';
import '../coding/coding.css';

interface Problem {
  id: string; title: string; difficulty: string; topics: string[]; statement: string;
  constraints: string[]; examples: { input: unknown[]; output: unknown; explanation?: string }[];
  sample_test_cases: CodingCase[]; entry_point: string; parameter_names: string[];
}
export default function CodingWorkspacePage() {
  const { sessionId = '' } = useParams();
  return <CodingWorkspace sessionId={sessionId}/>;
}

export function CodingWorkspace({ sessionId, embedded = false, onSubmitted, onEnd }: {
  sessionId: string; embedded?: boolean; onSubmitted?: () => void; onEnd?: () => void;
}) {
  const [problem, setProblem] = useState<Problem | null>(null);
  const [code, setCode] = useState('');
  const [results, setResults] = useState<CaseResult[]>([]);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState('');
  const [analysis, setAnalysis] = useState('');
  const [evaluation, setEvaluation] = useState<Record<string, unknown> | null>(null);
  const [followupFeedback, setFollowupFeedback] = useState('');
  const [followupBusy, setFollowupBusy] = useState(false);
  const [bank, setBank] = useState<{ id: string; title: string; difficulty: string; topics: string[] }[]>([]);

  useEffect(() => {
    let active = true;
    api.get<Problem>(`/interviews/${encodeURIComponent(sessionId)}/coding/problem`)
      .then(response => { if (active) {
        setProblem(response.data);
        const args = response.data.parameter_names.join(', ');
        setCode(`from typing import *\n\nclass Solution:\n    def ${response.data.entry_point}(self, ${args}):\n        pass\n`);
      } })
      .catch(cause => { if (active) setMessage(apiErrorMessage(cause, 'Could not load the coding problem.')); });
    api.get<{ problems: { id: string; title: string; difficulty: string; topics: string[] }[] }>('/interviews/coding/problems')
      .then(response => { if (active) setBank(response.data.problems); })
      .catch(() => { /* The active problem remains usable if the catalog request fails. */ });
    return () => { active = false; };
  }, [sessionId]);

  async function run(cases: CodingCase[]) {
    setBusy(true); setMessage('');
    try { const next = await executeCases(code, cases, 7000, problem?.entry_point); setResults(next); }
    catch (cause) { setMessage(cause instanceof Error ? cause.message : 'Pyodide could not start.'); }
    finally { setBusy(false); }
  }

  async function getCases(sampleOnly: boolean): Promise<CodingCase[]> {
    if (!problem) return [];
    const response = await api.post<{ cases: CodingCase[] }>(`/interviews/${encodeURIComponent(sessionId)}/coding/run`, {
      problem_id: problem.id, sample_only: sampleOnly,
    });
    return response.data.cases;
  }

  async function submit() {
    if (!problem) return;
    setBusy(true); setMessage('');
    try {
      const hiddenCases = await getCases(false);
      const fullResults = await executeCases(code, hiddenCases, 7000, problem.entry_point);
      setResults(fullResults);
      const response = await api.post(`/interviews/${encodeURIComponent(sessionId)}/coding/submit`, {
        problem_id: problem.id, submitted_code: code, results: fullResults, user_analysis: analysis,
      });
      setEvaluation(response.data);
      if (embedded) onSubmitted?.();
    } catch (cause) { setMessage(apiErrorMessage(cause, 'Could not submit this solution.')); }
    finally { setBusy(false); }
  }

  async function submitAnalysis() {
    if (!problem || !evaluation || !analysis.trim()) return;
    setFollowupBusy(true); setFollowupFeedback('');
    try {
      const response = await api.post(`/interviews/${encodeURIComponent(sessionId)}/coding/follow-up`, {
        problem_id: problem.id, submitted_code: code, user_analysis: analysis,
      });
      setFollowupFeedback(String(response.data.feedback ?? 'Follow-up saved.'));
    } catch (cause) { setMessage(apiErrorMessage(cause, 'Could not evaluate your follow-up.')); }
    finally { setFollowupBusy(false); }
  }

  if (!problem) return <div className={embedded ? 'coding-page coding-embedded' : 'page-content coding-page'}><p role="status">{message || 'Loading verified problem…'}</p></div>;
  const passed = results.filter(result => result.status === 'passed').length;
  return <div className={embedded ? 'coding-page coding-embedded' : 'page-content coding-page'}>
    <header className="coding-header"><div><span className="eyebrow">{embedded ? 'LIVE CODING EXERCISE' : `CODING INTERVIEW · ${bank.length} VERIFIED ${bank.length === 1 ? 'PROBLEM' : 'PROBLEMS'}`}</span><h1>{problem.title}</h1><p>{problem.difficulty} · {problem.topics.join(' · ')}</p></div>{embedded ? <button className="button button-outline" disabled={busy} onClick={onEnd}>End interview</button> : <Link className="button button-outline" to="/dashboard">Leave interview</Link>}</header>
    {!embedded && <details className="coding-bank glass-card"><summary>Problem bank <span>{bank.length} verified</span></summary><div>{bank.map(item => <p key={item.id}><strong>{item.title}</strong><span>{item.difficulty} · {item.topics.join(', ')}</span>{item.id === problem.id && <em>Current problem</em>}</p>)}</div></details>}
    <div className="coding-grid">
      <section className="coding-problem glass-card"><div className="coding-tabs">Problem <span>Python 3</span></div><article><h2>{problem.title}</h2><div className="coding-statement">{problem.statement}</div>
        <h3>Examples</h3>{problem.examples.map((example, index) => <div className="coding-example" key={index}><strong>Example {index + 1}</strong><code>Input: {JSON.stringify(example.input)}<br/>Output: {JSON.stringify(example.output)}</code>{example.explanation && <p>{example.explanation}</p>}</div>)}
        <h3>Constraints</h3><ul>{problem.constraints.map(value => <li key={value}><code>{value}</code></li>)}</ul>
      </article></section>
      <section className="coding-editor-panel glass-card"><div className="coding-tabs">Solution <span>Python 3 · Pyodide</span></div><Editor height="min(56vh, 620px)" language="python" theme="vs-dark" value={code} onChange={value => setCode(value ?? '')} options={{ minimap: { enabled: false }, fontSize: 14, padding: { top: 16 }, scrollBeyondLastLine: false, automaticLayout: true }} />
        <div className="coding-actions"><button className="button button-outline" disabled={busy} onClick={async () => { try { await run(await getCases(true)); } catch (cause) { setMessage(apiErrorMessage(cause, 'Could not load sample tests.')); } }}>{busy ? 'Running…' : 'Run samples'}</button><button className="button button-primary" disabled={busy} onClick={submit}>{busy ? 'Evaluating…' : 'Submit solution'}</button></div>
        {message && <p role="alert" className="interview-error">{message}</p>}
        <section className="coding-results" aria-label="Test results"><h3>Test results {results.length > 0 && <span>{passed}/{results.length} passed</span>}</h3>{results.map(result => <div className={`coding-result is-${result.status}`} key={result.index}><strong>Case {result.index + 1} · {result.status}</strong>{result.status === 'failed' && <code>Expected {JSON.stringify(result.expected)} · Got {JSON.stringify(result.actual)}</code>}{result.error && <code>{result.error}</code>}</div>)}</section>
        {!embedded && evaluation && <section className="coding-followup"><h3>Let’s discuss your approach</h3><p>{String(evaluation.passed)}/{String(evaluation.total)} tests passed. Complexity assessment: {evaluation.complexity_correct ? 'correct' : 'review'}</p><ul>{(evaluation.questions as string[] | undefined)?.map(question => <li key={question}>{question}</li>)}</ul><label htmlFor="coding-analysis">Your complexity and edge case analysis</label><textarea id="coding-analysis" value={analysis} onChange={event => setAnalysis(event.target.value)} placeholder="Explain your approach, time and space complexity, and edge cases." rows={4}/><button className="button button-primary" disabled={followupBusy || !analysis.trim()} onClick={submitAnalysis}>{followupBusy ? 'Reviewing…' : 'Submit analysis'}</button>{followupFeedback && <p role="status">{followupFeedback}</p>}</section>}
      </section>
    </div>
  </div>;
}
