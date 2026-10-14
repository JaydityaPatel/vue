import { useRef, useState, type FormEvent } from 'react';
import { ArrowRight, FileText, UploadCloud } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { BackLink, PageHeading } from '../components/AppShell';
import { createDocumentInterview } from '../api/interviews';
import { apiErrorMessage } from '../utils/errors';

export default function UploadSetupPage() {
  const { mode = 'resume' } = useParams();
  const job = mode === 'job';
  const navigate = useNavigate();
  const [resume, setResume] = useState<File | null>(null);
  const [jdFile, setJdFile] = useState<File | null>(null);
  const [jdText, setJdText] = useState('');
  const [role, setRole] = useState('');
  const [difficulty, setDifficulty] = useState('Balanced');
  const [duration, setDuration] = useState(30);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const submitting = useRef(false);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting.current) return;
    if (!resume) { setError('Choose your resume PDF to continue.'); return; }
    if (job && !jdFile && !jdText.trim()) { setError('Paste the job description or upload a PDF/.txt file.'); return; }
    submitting.current = true;
    setBusy(true);
    setError('');
    const form = new FormData();
    form.set('mode', mode === 'job' ? 'job' : 'resume');
    form.set('resume_file', resume);
    form.set('role', role.trim());
    form.set('experience', 'As described in the resume');
    form.set('difficulty', difficulty);
    form.set('interview_type', 'Mixed');
    form.set('duration', String(duration));
    if (jdText.trim()) form.set('jd_text', jdText);
    else if (jdFile) form.set('jd_file', jdFile);
    try {
      const session = await createDocumentInterview(form);
      navigate(`/interview/${session.session_id}/intro`, { state: { session } });
    } catch (cause) {
      setError(apiErrorMessage(cause, 'Could not prepare your interview. Check the documents and try again.'));
    } finally {
      submitting.current = false;
      setBusy(false);
    }
  }

  return <main className="page-content narrow-page setup-page">
    <BackLink to="/interview/new"/>
    <PageHeading eyebrow={job ? 'YOUR NEXT ROLE' : 'YOUR EXPERIENCE'}
      title={job ? 'Bring the role to life.' : 'Let’s start with your story.'}
      description={job ? 'We’ll compare the role with your experience and build a focused practice interview.'
        : 'We’ll use the projects and skills in your resume to shape your practice interview.'}/>
    <form className="glass-card setup-card upload-form" onSubmit={submit} aria-busy={busy}>
      <label className="field-label" htmlFor="resume">Your resume <span className="optional">PDF</span></label>
      <label className="upload-zone" htmlFor="resume">
        <input id="resume" type="file" accept="application/pdf,.pdf" disabled={busy}
          onChange={event => setResume(event.target.files?.[0] || null)}/>
        <span className="upload-icon"><UploadCloud size={20}/></span>
        <strong>{resume?.name || 'Choose a PDF to upload'}</strong>
        <span>{resume ? 'Ready to prepare your interview' : 'PDF with selectable text; scanned image-only PDFs are not supported'}</span>
      </label>
      <label className="field-label" htmlFor="role">Target role <span className="optional">OPTIONAL</span></label>
      <input className="text-input" id="role" maxLength={200} value={role} disabled={busy}
        onChange={event => setRole(event.target.value)} placeholder="e.g. Senior backend engineer"/>
      {job && <>
        <label className="field-label" htmlFor="job-description">Paste the job description</label>
        <textarea id="job-description" className="text-input" rows={6} maxLength={50000}
          value={jdText} disabled={busy} onChange={event => setJdText(event.target.value)}
          placeholder="Responsibilities, requirements, and qualifications…"/>
        <label className="field-label" htmlFor="jd-file">Or upload a job description <span className="optional">PDF OR TXT</span></label>
        <input id="jd-file" type="file" accept="application/pdf,.pdf,text/plain,.txt" disabled={busy}
          onChange={event => setJdFile(event.target.files?.[0] || null)}/>
        {jdFile && <p className="upload-note"><FileText size={16}/>{jdFile.name}</p>}
        <p className="upload-note">Pasted text takes precedence if you provide both.</p>
      </>}
      <div className="form-two-col">
        <div><label className="field-label" htmlFor="difficulty">Difficulty</label>
          <select id="difficulty" className="text-input" value={difficulty} disabled={busy} onChange={event => setDifficulty(event.target.value)}>
            <option>Gentle</option><option>Balanced</option><option>Challenging</option>
          </select>
        </div>
        <div><label className="field-label" htmlFor="duration">Practice time: {duration} min</label>
          <input className="range-input" id="duration" type="range" min="10" max="60" step="5" value={duration}
            disabled={busy} onChange={event => setDuration(Number(event.target.value))}/>
        </div>
      </div>
      {!job && <p className="upload-note"><FileText size={16}/>Contact email and phone numbers are removed before analysis. Your name is kept.</p>}
      {error && <p role="alert" className="interview-error">{error}</p>}
      {busy && <p className="setup-note" role="status" aria-live="polite">
        Vue is preparing your interview. We’re reading the documents and building questions from your experience. This can take 10–40 seconds.
      </p>}
      <button className="button button-primary submit-button" type="submit" disabled={busy}>
        {busy ? 'Preparing your interview…' : 'Continue to practice'} {!busy && <ArrowRight size={16}/>}
      </button>
    </form>
  </main>;
}
