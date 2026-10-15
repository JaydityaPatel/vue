import { useEffect, useState } from 'react';
import { ArrowRight, BookOpenCheck, MessageCircleMore, Puzzle, Target } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { generateReport, type InterviewReport } from '../api/interviews';
import { BackLink, PageHeading } from '../components/AppShell';

const metrics = [
  { key: 'technical_correctness', title: 'Technical correctness', icon: Target },
  { key: 'completeness', title: 'Completeness', icon: BookOpenCheck },
  { key: 'communication', title: 'Communication', icon: MessageCircleMore },
  { key: 'problem_solving', title: 'Problem-solving', icon: Puzzle },
];

export default function ReportPage() {
  const { sessionId = '' } = useParams();
  const [report, setReport] = useState<InterviewReport | null>(null);
  const [error, setError] = useState('');
  useEffect(() => { generateReport(sessionId).then(setReport).catch(() => setError('The report is not available yet.')); }, [sessionId]);
  return <main className="page-content report-page"><BackLink to="/history">Back to history</BackLink>
    <PageHeading eyebrow="A MOMENT TO REFLECT" title="Your practice report" description="Review the evidence from your interview and choose what to work on next."/>
    {error && <p role="alert" className="interview-error">{error}</p>}
    {!report && !error && <p role="status">Preparing your report…</p>}
    {report && <>
      <div className="report-banner glass-card"><span className="report-icon"><BookOpenCheck size={20}/></span><div><h2>Overall score: {report.overall_score.toFixed(2)} / 5</h2><p>{report.summary}</p>{report.provisional && <small>This report uses a fallback evaluation model.</small>}</div></div>
      <section className="score-grid" aria-label="Score breakdown">{metrics.map(({key,title,icon:Icon})=><article className="score-card glass-card" key={key}><Icon size={17}/><h3>{title}</h3><p>{report.dimension_breakdown?.[key] == null ? '—' : `${report.dimension_breakdown[key].toFixed(2)} / 5`}</p></article>)}</section>
      {report.coding_breakdown && <section className="glass-card report-section coding-report" aria-label="Coding round breakdown"><div className="eyebrow"><span/>CODING ROUND</div><h2>{report.coding_breakdown.problems_solved}/{report.coding_breakdown.problems_total} problems solved</h2><p>{report.coding_breakdown.tests_passed}/{report.coding_breakdown.tests_total} test cases passed · correct complexity analysis on {report.coding_breakdown.complexity_correct}/{report.coding_breakdown.complexity_total}</p></section>}
      <section className="section-block"><div className="eyebrow"><span/>NEXT STEPS</div><h2>Improvement suggestions</h2><ul>{report.improvement_suggestions.map((item,index)=><li key={index}>{item}</li>)}</ul></section>
      <section className="section-block report-transcript"><div className="eyebrow"><span/>YOUR ANSWERS</div><h2>Turn-by-turn review</h2>
        {(report.turns ?? []).map(turn=><article className="glass-card report-turn" key={turn.id}><div className="eyebrow"><span/>{turn.topic} · {turn.topic_type === 'coding' ? 'Coding' : 'Discussion'}</div><h3>{turn.question}</h3><p className="report-answer">{turn.answer || 'No spoken answer recorded.'}</p>
          {turn.scores && <div className="turn-score-row">{metrics.map(({key,title})=><span key={key}>{title}: <b>{turn.scores?.[key]?.toFixed(1) ?? '—'}</b></span>)}</div>}
          {turn.expected_concepts.length > 0 && <p><b>Expected:</b> {turn.expected_concepts.join(', ')}</p>}{turn.missing_concepts.length > 0 && <p><b>To strengthen:</b> {turn.missing_concepts.join(', ')}</p>}
          {turn.skill_tags.length > 0 && <p><b>Skills:</b> {turn.skill_tags.join(', ')}</p>}{turn.feedback && <p>{turn.feedback}</p>}{turn.tests_total != null && <p>Tests: {turn.tests_passed ?? 0}/{turn.tests_total} passed</p>}
        </article>)}
      </section>
      <Link className="button button-primary report-cta" to="/interview/new">Try another practice <ArrowRight size={16}/></Link>
    </>}
  </main>;
}
