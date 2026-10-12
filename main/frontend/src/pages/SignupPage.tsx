import { useState, type FormEvent } from 'react';
import { motion } from 'framer-motion';
import { ArrowRight, Eye, EyeOff, LockKeyhole, Mail, UserRound } from 'lucide-react';
import { Link, useNavigate } from 'react-router-dom';
import Brand from '../components/Brand';
import { useAuth } from '../context/AuthContext';
import { apiErrorMessage } from '../utils/errors';

export default function SignupPage() {
  const { register } = useAuth(); const navigate = useNavigate();
  const [name, setName] = useState(''); const [email, setEmail] = useState(''); const [password, setPassword] = useState('');
  const [error, setError] = useState(''); const [busy, setBusy] = useState(false); const [showPassword, setShowPassword] = useState(false);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault(); setError('');
    if (password.length < 8) { setError('Use at least 8 characters for your password.'); return; }
    setBusy(true);
    try { await register({ email, password, full_name: name.trim() || undefined }); navigate('/dashboard', { replace: true }); }
    catch (cause) { setError(apiErrorMessage(cause, 'We couldn’t create your account. Please try again.')); }
    finally { setBusy(false); }
  }
  return <main className="auth-layout">
    <aside className="auth-aside signup-aside"><Brand /><div className="auth-aside-copy"><div className="eyebrow"><span/>MAKE THIS SPACE YOURS</div><h2>Practice makes the moment feel familiar.</h2><p>A little preparation goes a long way. Let’s make a space for yours.</p><div className="signup-quote glass-card"><span>“</span><p>Confidence isn’t knowing every answer. It’s feeling ready to start.</p><small>A thought worth carrying with you</small></div></div><p className="aside-footnote">YOUR NEXT CHAPTER STARTS HERE</p></aside>
    <section className="auth-main"><div className="auth-top-note">Already have an account? <Link to="/login">Sign in <ArrowRight size={14}/></Link></div><motion.div className="auth-card-wrap" initial={{ opacity: 0, y: 12 }} animate={{ opacity: 1, y: 0 }} transition={{ duration: .4 }}>
      <div className="auth-heading"><div className="auth-symbol"><UserRound size={19}/></div><div className="eyebrow"><span/>A GOOD PLACE TO BEGIN</div><h1>Let’s get to know you.</h1><p>Set up your account. Your next practice run awaits.</p></div>
      <form className="form-stack" onSubmit={submit} noValidate>
        <label className="field-label" htmlFor="name">Your name <span className="optional">OPTIONAL</span></label><div className="input-wrap"><UserRound size={17}/><input id="name" type="text" value={name} onChange={event=>setName(event.target.value)} autoComplete="name" placeholder="How should we greet you?" maxLength={120}/></div>
        <label className="field-label" htmlFor="email">Email address</label><div className="input-wrap"><Mail size={17}/><input id="email" type="email" value={email} onChange={event=>setEmail(event.target.value)} autoComplete="email" placeholder="you@example.com" required/></div>
        <label className="field-label" htmlFor="password">Create a password</label><div className="input-wrap"><LockKeyhole size={17}/><input id="password" type={showPassword?'text':'password'} value={password} onChange={event=>setPassword(event.target.value)} autoComplete="new-password" placeholder="At least 8 characters" required aria-describedby={error?'signup-error':undefined}/><button className="reveal-button" type="button" aria-label={showPassword?'Hide password':'Show password'} onClick={()=>setShowPassword(!showPassword)}>{showPassword?<EyeOff size={17}/>:<Eye size={17}/>}</button></div>
        {error && <p className="form-error" role="alert" id="signup-error">{error}</p>}
        <button className="button button-primary submit-button" type="submit" disabled={busy}>{busy?'Creating your space…':'Create account'} <ArrowRight size={16}/></button>
      </form><div className="auth-bottom">By joining, you’re making space for your own progress.</div>
    </motion.div></section>
  </main>;
}
