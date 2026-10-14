// Original demo's three folded sheets: detail comes from point shaders, not a sphere mesh.
export const quad = new Float32Array([-1,-1,0, 1,-1,0, -1,1,0, -1,1,0, 1,-1,0, 1,1,0]);
export const seeds = new Float32Array(Array.from({ length: 3 * 72 * 128 }, (_, i) => {
  const layer = Math.floor(i / (72 * 128));
  const row = Math.floor(i / 128) % 72;
  const column = i % 128;
  return [(column + .5) / 128 * 2 - 1, row / 71 * 2 - 1, layer - 1];
}).flat());
