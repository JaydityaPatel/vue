import { ArrowRight, Mail, UserRound } from 'lucide-react';
import { Link } from 'react-router-dom';
import { PageHeading } from '../components/AppShell';
import { useAuth } from '../context/AuthContext';

export default function ProfilePage(){const {user}=useAuth();return <main className="page-content narrow-page"><PageHeading eyebrow="YOUR CORNER OF VUE" title="Your profile." description="The details you brought with you."/><section className="profile-card glass-card"><div className="profile-avatar"><UserRound size={26}/></div><div className="profile-details"><div><span className="profile-field"><UserRound size={15}/>NAME</span><strong>{user?.full_name||'Not added yet'}</strong></div><div><span className="profile-field"><Mail size={15}/>EMAIL</span><strong>{user?.email}</strong></div></div></section><div className="profile-next"><span>Want to get back to it?</span><Link className="text-link" to="/dashboard">Back to your practice space <ArrowRight size={15}/></Link></div></main>}
