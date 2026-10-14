/** Own the draw clock: prop updates must not bypass the GPU frame limit. */
export function startOrbLoop(draw: (seconds: number) => void, sttActive: boolean): () => void {
  let frame = 0;
  let previous = 0;
  const tick = (time: number) => {
    if (!document.hidden && time - previous >= 1000 / (sttActive ? 10 : 30)) {
      draw(time / 1000);
      previous = time;
    }
    frame = requestAnimationFrame(tick);
  };
  frame = requestAnimationFrame(tick);
  return () => cancelAnimationFrame(frame);
}
