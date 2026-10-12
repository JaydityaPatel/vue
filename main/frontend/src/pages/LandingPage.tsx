import { motion } from 'framer-motion';
import { ArrowRight, AudioLines, BrainCircuit, BriefcaseBusiness, FileUser, Mic2, Sparkles, Target } from 'lucide-react';
import { Link } from 'react-router-dom';
import Brand from '../components/Brand';
import FeatureCard from '../components/FeatureCard';

export default function LandingPage() {
  return <div className="landing">
    <div className="hero-neon-arc" aria-hidden="true"><span/></div>
    <nav className="landing-nav glass-nav"><Brand /><div className="landing-links"><a href="#approach">How it works</a><a href="#modes">Modes</a><Link className="landing-login" to="/login">I have an account</Link><Link className="nav-get-started" to="/signup">Get Started <ArrowRight size={14}/></Link></div></nav>
    <section className="hero">
      <div className="hero-glow" />
      <motion.div className="hero-copy" initial={{ opacity: 0, y: 18 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .7 }}>
        <div className="eyebrow"><span />A calmer way to prepare</div>
        <h1>Make room for<br/><span>your best answer.</span></h1>
        <p className="hero-description">Thoughtful mock interviews shaped around a role, your resume, or the skills you want to explore.</p>
      </motion.div>
      {/* Visual-only product preview; the interactive voice experience arrives with Phase 5. */}
      <motion.div className="preview-wrap" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .55, delay: .12 }}>
        <Link className="preview-panel glass-card" to="/signup" aria-label="Start practicing: paste a job description or upload your resume">
          <div className="preview-topline"><span className="preview-icon"><AudioLines size={17}/></span><span className="preview-kicker">A PLACE TO BEGIN</span><span className="preview-status"><i/> READY WHEN YOU ARE</span></div>
          <p className="preview-prompt">Paste a job description or upload your resume to begin<span className="preview-cursor"/></p>
          <div className="preview-bottom"><span className="preview-mic"><Mic2 size={16}/><span>No setup needed to explore</span></span><span className="button button-primary preview-cta">Start Practicing <ArrowRight size={15}/></span></div>
        </Link>
      </motion.div>
    </section>
    <section className="mode-strip" id="modes"><span className="mode-strip-label">A FEW WAYS TO BEGIN</span><div className="mode-strip-items"><span><BriefcaseBusiness/>Job Interviews</span><i/><span><FileUser/>Resume Deep-Dives</span><i/><span><Sparkles/>Random Practice</span></div></section>
    <section id="approach" className="approach-section"><div className="section-intro"><div className="eyebrow"><span />Practice with purpose</div><h2>Less pressure.<br /><span>More presence.</span></h2><p>Good interviews start before you walk in. Take a breath, get curious, and practice in a space that’s yours.</p></div><div className="feature-grid"><FeatureCard index={0} icon={<AudioLines />} title="Find your voice" text="Rehearse out loud and get comfortable explaining how you think."/><FeatureCard index={1} icon={<Target />} title="Make it relevant" text="Shape each practice session around the role and work ahead of you."/><FeatureCard index={2} icon={<BrainCircuit />} title="Learn as you go" text="See what’s landing, what to revisit, and where your answer shines."/></div></section>
    <section className="final-cta"><span className="cta-orb"><Sparkles /></span><p>There’s no perfect answer. Just your next one.</p><Link className="button button-primary" to="/signup">Start practicing <ArrowRight size={16}/></Link></section>
    <footer className="landing-footer"><Brand /><span>A quieter corner of the internet to work on what’s next.</span><Link to="/login">Welcome back <ArrowRight size={14}/></Link></footer>
  </div>;
}
