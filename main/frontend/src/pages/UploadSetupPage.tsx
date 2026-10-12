import { useState, type FormEvent } from 'react';
import { ArrowRight, FileText, UploadCloud } from 'lucide-react';
import { useNavigate, useParams } from 'react-router-dom';
import { BackLink, PageHeading } from '../components/AppShell';

export default function UploadSetupPage() {
  const { mode='resume' }=useParams(); const navigate=useNavigate(); const [resume,setResume]=useState<File|null>(null); const [description,setDescription]=useState('');
  const job=mode==='job';
  function submit(event:FormEvent<HTMLFormElement>){event.preventDefault();const id=crypto.randomUUID();sessionStorage.setItem(`vue-session:${id}`,JSON.stringify({mode,role:'',resumeName:resume?.name||null,jobDescription:description}));navigate(`/interview/${id}`);}
  return <main className="page-content narrow-page setup-page"><BackLink to="/interview/new"/><PageHeading eyebrow={job?'YOUR NEXT ROLE':'YOUR EXPERIENCE'} title={job?'Bring the role to life.':'Let’s start with your story.'} description={job?'Add your resume and some context about the opportunity.':'Upload your resume so you can practice talking through your experience.'}/><form className="glass-card setup-card upload-form" onSubmit={submit}>
    <label className="field-label" htmlFor="resume">Your resume <span className="optional">PDF</span></label><label className="upload-zone" htmlFor="resume"><input id="resume" type="file" accept="application/pdf,.pdf" onChange={event=>setResume(event.target.files?.[0]||null)}/><span className="upload-icon"><UploadCloud size={20}/></span><strong>{resume?.name||'Choose a PDF to upload'}</strong><span>{resume?'Ready for your practice session':'Your file stays on this device for now'}</span></label>
    {job&&<><label className="field-label" htmlFor="job-description">Job description <span className="optional">OPTIONAL</span></label><textarea id="job-description" className="text-input" rows={6} value={description} onChange={event=>setDescription(event.target.value)} placeholder="Paste the job description or a few details about the role…"/></>}
    {!job&&<div className="upload-note"><FileText size={16}/>We’ll use this as a prompt for your practice. Resume parsing is coming in a later update.</div>}
    <button className="button button-primary submit-button" type="submit">Continue to practice <ArrowRight size={16}/></button>
  </form></main>;
}
