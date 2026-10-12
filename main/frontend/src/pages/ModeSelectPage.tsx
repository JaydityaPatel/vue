import { motion } from 'framer-motion';
import { ArrowRight, BriefcaseBusiness, FileUser, Shuffle } from 'lucide-react';
import { Link } from 'react-router-dom';
import { BackLink, PageHeading } from '../components/AppShell';

const modes = [
  { id: 'job', icon: BriefcaseBusiness, title: 'Job interview', copy: 'Bring the role and the job description. Let’s make practice feel closer to the real thing.', label: 'A role you’re pursuing', tone: 'violet' },
  { id: 'resume', icon: FileUser, title: 'Resume interview', copy: 'Share your experience and get ready to talk through the work that shaped you.', label: 'Your experience, in focus', tone: 'blue' },
  { id: 'random', icon: Shuffle, title: 'Random interview', copy: 'Explore common interview questions, stretch your thinking, and see what surfaces.', label: 'Practice for anything', tone: 'amber' },
];

export default function ModeSelectPage() {
  return <main className="page-content narrow-page"><BackLink to="/dashboard"/> <PageHeading eyebrow="CHOOSE YOUR STARTING POINT" title="What are we preparing for?" description="Pick a format. You can shape the details in the next step."/><div className="mode-grid">{modes.map((mode, index) => {const Icon=mode.icon; return <motion.div key={mode.id} initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: index*.08 }}><Link className={`mode-card glass-card ${mode.tone}`} to={mode.id==='random'?'/interview/new/random':`/interview/new/${mode.id}`}><div className="mode-icon"><Icon size={21}/></div><span className="mode-label">{mode.label}</span><h2>{mode.title}</h2><p>{mode.copy}</p><span className="mode-action">Let’s set it up <ArrowRight size={15}/></span></Link></motion.div>;})}</div></main>;
}
