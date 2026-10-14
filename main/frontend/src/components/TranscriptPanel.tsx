import { useEffect, useRef } from 'react';
import type { InterviewTurn } from '../api/interviews';

export default function TranscriptPanel({ turns, partial }: { turns: InterviewTurn[]; partial: string }) {
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => { bottom.current?.scrollIntoView?.({ behavior: 'smooth', block: 'end' }); }, [turns, partial]);
  return <aside className="glass-card voice-transcript" aria-label="Conversation">
    <div className="transcript-heading"><h2>Conversation</h2><span>{turns.length} questions</span></div>
    <div className="voice-transcript-scroll" role="log" aria-live="polite" aria-relevant="additions text">
      {turns.map(turn => <section key={turn.id} className="voice-turn">
        <div className="voice-message"><h3>Vue</h3><p>{turn.question_text}</p></div>
        {turn.answer_text !== null && <div className="voice-message candidate-answer"><h3>You</h3><p>{turn.answer_text}</p></div>}
      </section>)}
      {partial && <div className="voice-message voice-partial"><h3>You <small>Transcribing…</small></h3><p>{partial}</p></div>}
      <div ref={bottom} data-testid="transcript-bottom"/>
    </div>
  </aside>;
}
