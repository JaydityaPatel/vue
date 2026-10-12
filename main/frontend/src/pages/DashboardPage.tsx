import { motion } from 'framer-motion';
import { ArrowRight, ArrowUpRight, AudioLines, Clock3, Sparkles } from 'lucide-react';
import { Link } from 'react-router-dom';
import { PageHeading } from '../components/AppShell';
import { useAuth } from '../context/AuthContext';

export default function DashboardPage() {
  const { user } = useAuth();
  const hour = new Date().getHours();
  const greeting = hour < 12 ? 'Good morning' : hour < 18 ? 'Good afternoon' : 'Good evening';
  return <main className="page-content dashboard-page">
    <PageHeading eyebrow="YOUR PRACTICE SPACE" title={`${greeting}${user?.full_name ? `, ${user.full_name.split(' ')[0]}` : ''}.`} description="No rush. Just a little room to get ready for what’s next." />
    <motion.section className="dashboard-hero glass-card" initial={{ opacity: 0, y: 14 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .45 }}>
      <div className="dashboard-hero-copy"><div className="eyebrow"><span/>THE NEXT STEP IS YOURS</div><h2>One thoughtful<br/><span>practice run.</span></h2><p>Choose the conversation you’re preparing for. We’ll meet you there.</p><Link className="button button-primary" to="/interview/new">Start a new interview <ArrowRight size={16}/></Link></div>
      <div className="dashboard-art" aria-hidden="true"><div className="dashboard-orbit orbit-a"/><div className="dashboard-orbit orbit-b"/><div className="dashboard-sphere"><AudioLines size={37}/></div><div className="dashboard-art-label"><Sparkles size={14}/> YOUR PACE. YOUR SPACE.</div></div>
    </motion.section>
    <section className="section-block"><div className="section-title-row"><div><div className="eyebrow"><span/>KEEP YOUR MOMENTUM</div><h2>Recent sessions</h2></div><Link className="text-link" to="/history">View history <ArrowUpRight size={15}/></Link></div>
      <div className="empty-panel glass-card"><span className="empty-icon"><Clock3 size={19}/></span><h3>Your story starts here.</h3><p>Your recent practice sessions will find a home here. Ready for the first one?</p><Link className="text-link" to="/interview/new">Set up your first interview <ArrowRight size={15}/></Link></div>
    </section>
  </main>;
}
