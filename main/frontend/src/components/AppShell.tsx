import { Link, NavLink, Outlet, useNavigate } from 'react-router-dom';
import { ArrowUpRight, CircleUserRound, Command, LogOut, PanelsTopLeft, Sparkles } from 'lucide-react';
import { useAuth } from '../context/AuthContext';

export default function AppShell() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  return (
    <div className="app-frame">
      <header className="app-header">
        <Link className="brand" to="/dashboard"><span className="brand-icon"><Command size={18} /></span><span>vue<span className="brand-dot">.</span></span></Link>
        <nav className="top-nav" aria-label="Main navigation">
          <NavLink to="/dashboard"><PanelsTopLeft size={15} />Dashboard</NavLink>
          <NavLink to="/history">History</NavLink>
        </nav>
        <div className="account-area"><span className="account-email">{user?.email}</span><button className="avatar" aria-label="Profile" onClick={() => navigate('/profile')}><CircleUserRound size={19} /></button><button className="icon-button" aria-label="Sign out" onClick={() => { logout(); navigate('/login', { replace: true }); }}><LogOut size={16} /></button></div>
      </header>
      <Outlet />
      <footer className="app-footer"><span>vue<span className="brand-dot">.</span> interview practice</span><span>Made for your next chapter <Sparkles size={13} /></span></footer>
    </div>
  );
}

export function PageHeading({ eyebrow, title, description }: { eyebrow: string; title: string; description?: string }) {
  return <div className="page-heading"><div className="eyebrow"><span />{eyebrow}</div><h1>{title}</h1>{description && <p>{description}</p>}</div>;
}

export function BackLink({ to, children = 'Back' }: { to: string; children?: string }) {
  return <Link className="back-link" to={to}><ArrowUpRight size={14} className="back-arrow" />{children}</Link>;
}
