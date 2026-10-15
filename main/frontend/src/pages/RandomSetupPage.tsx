import { useRef, useState, type FormEvent } from 'react';
import { ArrowRight, Check, Sparkles } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { BackLink, PageHeading } from '../components/AppShell';
import { createInterview, type InterviewConfig } from '../api/interviews';
import { apiErrorMessage } from '../utils/errors';

export default function RandomSetupPage() {
  const navigate = useNavigate(); const [role,setRole]=useState(''); const [experience,setExperience]=useState('Mid-level'); const [skills,setSkills]=useState(''); const [difficulty,setDifficulty]=useState('Balanced'); const [type,setType]=useState('Mixed'); const [duration,setDuration]=useState(30);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const submitting = useRef(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    submitting.current = true;
    setBusy(true);
    setError('');
    try {
      const session = await createInterview({
        role: role.trim(), experience,
        skills: skills.split(',').map(skill => skill.trim()).filter(Boolean),
        difficulty: difficulty as InterviewConfig['difficulty'],
        interview_type: type as InterviewConfig['interview_type'], duration,
      });
        navigate(type === 'Coding' ? `/interview/${session.session_id}/coding` : `/interview/${session.session_id}`, { state: { session } });
    } catch (cause) {
      setError(apiErrorMessage(cause, 'Could not start the interview. Please try again.'));
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }
  return <main className="page-content narrow-page setup-page"><BackLink to="/interview/new"/><PageHeading eyebrow="A LITTLE CONTEXT GOES A LONG WAY" title="Make it yours." description="A few details help us shape a practice that feels relevant to you."/><form className="glass-card setup-card" onSubmit={submit}>
    <label className="field-label" htmlFor="role">Target role <span className="optional">OPTIONAL</span></label><input className="text-input" id="role" value={role} onChange={event=>setRole(event.target.value)} placeholder="e.g. Product designer"/>
    <label className="field-label" htmlFor="experience">Experience level</label><select className="text-input" id="experience" value={experience} onChange={event=>setExperience(event.target.value)}><option>Entry-level</option><option>Mid-level</option><option>Senior</option><option>Lead / Principal</option></select>
    <label className="field-label" htmlFor="skills">Skills or topics to practice</label><textarea className="text-input" id="skills" value={skills} onChange={event=>setSkills(event.target.value)} placeholder="Type a few, separated by commas" rows={3}/>
    <div className="form-two-col"><div><label className="field-label" htmlFor="difficulty">Difficulty</label><select className="text-input" id="difficulty" value={difficulty} onChange={event=>setDifficulty(event.target.value)}><option>Gentle</option><option>Balanced</option><option>Challenging</option></select></div><div><label className="field-label" htmlFor="type">Interview style</label><select className="text-input" id="type" value={type} onChange={event=>setType(event.target.value)}><option>Mixed</option><option>Technical</option><option>Coding</option><option>Behavioral</option><option>System design</option></select></div></div>
    <div className="range-heading"><label className="field-label" htmlFor="duration">Practice time</label><span>{duration} min</span></div><input className="range-input" id="duration" type="range" min="10" max="60" step="5" value={duration} onChange={event=>setDuration(Number(event.target.value))}/><div className="range-labels"><span>10 min</span><span>60 min</span></div>
    <div className="setup-note"><Sparkles size={15}/><span>Your practice is ready when you are.</span><Check size={14}/></div>
    {error && <p role="alert" className="interview-error">{error}</p>}
    <button className="button button-primary submit-button" type="submit" disabled={busy}>{busy ? 'Preparing your interview...' : 'Start practice'} <ArrowRight size={16}/></button>
  </form></main>;
}
