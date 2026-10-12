import { useState, type FormEvent } from 'react';
import { motion } from 'framer-motion';
import { ArrowRight, Eye, EyeOff, LockKeyhole, Mail } from 'lucide-react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import Brand from '../components/Brand';
import { useAuth } from '../context/AuthContext';
import { apiErrorMessage } from '../utils/errors';

export default function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError(''); setBusy(true);
    try { await login(email, password); navigate(location.state?.from || '/dashboard', { replace: true }); }
    catch (cause) { setError(apiErrorMessage(cause, 'We couldn’t sign you in. Check your details and try again.')); }
    finally { setBusy(false); }
  }
  return <main className="auth-layout">
    <aside className="auth-aside"><Brand /><div className="auth-aside-copy"><div className="eyebrow"><span/>A space to practice</div><h2>Your next opportunity is a conversation away.</h2><p>Take the time to find your words. The confidence follows.</p><div className="aside-decoration"><div className="aside-orbit one"/><div className="aside-orbit two"/><div className="aside-dot"><span/><i/></div></div></div><p className="aside-footnote">A LITTLE SPACE TO THINK</p></aside>
    <section className="auth-main"><div className="auth-top-note">New to Vue? <Link to="/signup">Create an account <ArrowRight size={14}/></Link></div><motion.div className="auth-card-wrap" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .4 }}>
      <div className="auth-heading"><div className="auth-symbol"><LockKeyhole size={19}/></div><div className="eyebrow"><span/>PICK UP WHERE YOU LEFT OFF</div><h1>Welcome back.</h1><p>Sign in to continue your practice.</p></div>
      <form className="form-stack" onSubmit={submit} noValidate>
        <label className="field-label" htmlFor="email">Email address</label><div className="input-wrap"><Mail size={17}/><input id="email" type="email" value={email} onChange={event=>setEmail(event.target.value)} autoComplete="email" placeholder="you@example.com" required /></div>
        <div className="field-row"><label className="field-label" htmlFor="password">Password</label></div><div className="input-wrap"><LockKeyhole size={17}/><input id="password" type={showPassword?'text':'password'} value={password} onChange={event=>setPassword(event.target.value)} autoComplete="current-password" placeholder="Your password" required/><button className="reveal-button" type="button" aria-label={showPassword?'Hide password':'Show password'} onClick={()=>setShowPassword(!showPassword)}>{showPassword?<EyeOff size={17}/>:<Eye size={17}/>}</button></div>
        {error && <p className="form-error" role="alert">{error}</p>}
        <button className="button button-primary submit-button" type="submit" disabled={busy}>{busy?'Signing in…':'Sign in'} <ArrowRight size={16}/></button>
      </form><div className="auth-bottom">Your practice space is private and yours alone.</div>
    </motion.div></section>
  </main>;
}
