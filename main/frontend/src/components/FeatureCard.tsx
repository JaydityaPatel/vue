import type { ReactNode } from 'react';
import { motion } from 'framer-motion';

export default function FeatureCard({ icon, title, text, index }: { icon: ReactNode; title: string; text: string; index: number }) {
  return <motion.article className="feature-card glass-card" initial={{ opacity: 0, y: 18 }} whileInView={{ opacity: 1, y: 0 }} viewport={{ once: true }} transition={{ duration: .5, delay: index * .09 }}><span className="feature-icon">{icon}</span><h3>{title}</h3><p>{text}</p></motion.article>;
}
