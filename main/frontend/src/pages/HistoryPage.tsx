import { ArrowRight, Clock3 } from 'lucide-react';
import { Link } from 'react-router-dom';
import { PageHeading } from '../components/AppShell';

export default function HistoryPage(){return <main className="page-content"><PageHeading eyebrow="YOUR JOURNEY SO FAR" title="A practice, in progress." description="Your past sessions will gather here, whenever you’re ready."/><section className="empty-panel glass-card history-empty"><span className="empty-icon"><Clock3 size={19}/></span><h2>Nothing to look back on just yet.</h2><p>Each practice is a small step forward. Your first one can start whenever you are.</p><Link className="button button-primary" to="/interview/new">Start a practice <ArrowRight size={16}/></Link></section></main>}
