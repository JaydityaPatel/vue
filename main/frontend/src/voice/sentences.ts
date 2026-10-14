/** Retain incomplete words/sentences across arbitrary transport boundaries. */
export class SentenceBuffer {
  private text = '';
  push(chunk: string, final = false): string[] {
    this.text += chunk;
    const ready: string[] = [];
    let start = 0;
    for (let i = 0; i < this.text.length; i++) {
      if (!/[.!?]/.test(this.text[i])) continue;
      let end = i + 1;
      while (end < this.text.length && /[.!?"'”’)]/.test(this.text[end])) end++;
      if (end === this.text.length && !final) continue;
      if (end < this.text.length && !/\s/.test(this.text[end])) continue;
      const prefix = this.text.slice(start, i + 1);
      if (this.text[i] === '.' && /(?:\b(?:Mr|Mrs|Ms|Dr|Prof|Sr|Jr|vs|etc)|\b[A-Z]|\be\.g|\bi\.e|\b(?:[A-Z]\.)+[A-Z])\.$/i.test(prefix)) continue;
      ready.push(this.text.slice(start, end).trim());
      start = end;
      i = end - 1;
    }
    this.text = this.text.slice(start).trimStart();
    if (final && this.text.trim()) { ready.push(this.text.trim()); this.text = ''; }
    return ready;
  }
}
