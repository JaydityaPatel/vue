import { Link } from 'react-router-dom';
import { Command } from 'lucide-react';

export default function Brand() {
  return <Link className="brand" to="/"><span className="brand-icon"><Command size={18} /></span><span>vue<span className="brand-dot">.</span></span></Link>;
}
