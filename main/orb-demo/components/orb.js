import { quadVertex, ringFragment, particleVertex, particleFragment } from '../shaders/orb.js';

export class Orb {
  constructor(canvas, audio) {
    this.canvas = canvas;
    this.audio = audio;
    this.gl = canvas.getContext('webgl', { alpha: false, antialias: false, powerPreference: 'high-performance', preserveDrawingBuffer: false });
    if (!this.gl) throw new Error('WebGL is unavailable. Enable hardware acceleration to view the orb.');
    this.pointer = [0, 0];
    this.targetPointer = [0, 0];
    this.time = 0;
    this.frames = 0;
    this.disposed = false;
    this.reducedMotion = matchMedia('(prefers-reduced-motion: reduce)');
    this.initialize();
    this.resizeObserver = new ResizeObserver(() => this.resize());
    this.resizeObserver.observe(canvas);
    this.move = event => {
      const rect = canvas.getBoundingClientRect();
      this.targetPointer = [(event.clientX - rect.left) / rect.width * 2 - 1, 1 - (event.clientY - rect.top) / rect.height * 2];
    };
    this.leave = () => { this.targetPointer = [0, 0]; };
    this.lost = event => { event.preventDefault(); cancelAnimationFrame(this.frame); };
    this.restored = () => { this.initialize(); this.resize(); this.previous = 0; this.frame = requestAnimationFrame(this.render); };
    this.visibility = () => {
      cancelAnimationFrame(this.frame);
      if (!document.hidden) { this.previous = 0; this.frame = requestAnimationFrame(this.render); }
    };
    canvas.addEventListener('pointermove', this.move);
    canvas.addEventListener('pointerleave', this.leave);
    canvas.addEventListener('webglcontextlost', this.lost);
    canvas.addEventListener('webglcontextrestored', this.restored);
    document.addEventListener('visibilitychange', this.visibility);
    this.render = this.render.bind(this);
    this.resize();
    this.frame = requestAnimationFrame(this.render);
  }

  program(vertex, fragment) {
    const gl = this.gl;
    const shaders = [[gl.VERTEX_SHADER, vertex], [gl.FRAGMENT_SHADER, fragment]].map(([kind, source]) => {
      const shader = gl.createShader(kind);
      gl.shaderSource(shader, source);
      gl.compileShader(shader);
      if (!gl.getShaderParameter(shader, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(shader));
      return shader;
    });
    const program = gl.createProgram();
    shaders.forEach(shader => gl.attachShader(program, shader));
    gl.linkProgram(program);
    shaders.forEach(shader => gl.deleteShader(shader));
    if (!gl.getProgramParameter(program, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(program));
    const uniforms = {};
    for (const name of ['time', 'audio', 'pointer', 'pixelRatio', 'viewport']) uniforms[name] = gl.getUniformLocation(program, name);
    return { program, uniforms };
  }

  initialize() {
    const gl = this.gl;
    this.ring = this.program(quadVertex, ringFragment);
    this.particles = this.program(particleVertex, particleFragment);
    this.quad = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.quad);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 1,-1, -1,1, -1,1, 1,-1, 1,1]), gl.STATIC_DRAW);
    const seeds = [];
    for (let layer = 0; layer < 3; layer++) {
      for (let row = 0; row < 72; row++) {
        for (let col = 0; col < 128; col++) seeds.push((col + .5) / 128 * 2 - 1, row / 71 * 2 - 1, layer - 1);
      }
    }
    this.count = seeds.length / 3;
    this.points = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, this.points);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(seeds), gl.STATIC_DRAW);
  }

  resize() {
    const size = this.canvas.getBoundingClientRect().width;
    this.ratio = Math.min(devicePixelRatio || 1, 2);
    this.size = size;
    this.canvas.width = this.canvas.height = Math.max(1, Math.round(size * this.ratio));
    this.gl.viewport(0, 0, this.canvas.width, this.canvas.height);
  }

  draw(pass, buffer, attribute, components, mode, count, bands) {
    const gl = this.gl;
    gl.useProgram(pass.program);
    gl.bindBuffer(gl.ARRAY_BUFFER, buffer);
    const location = gl.getAttribLocation(pass.program, attribute);
    gl.enableVertexAttribArray(location);
    gl.vertexAttribPointer(location, components, gl.FLOAT, false, 0, 0);
    gl.uniform1f(pass.uniforms.time, this.time);
    gl.uniform4f(pass.uniforms.audio, bands.bass, bands.mid, bands.high, bands.level);
    gl.uniform2fv(pass.uniforms.pointer, this.pointer);
    gl.uniform1f(pass.uniforms.pixelRatio, this.ratio);
    gl.uniform1f(pass.uniforms.viewport, this.size);
    gl.drawArrays(mode, 0, count);
    gl.disableVertexAttribArray(location);
  }

  render(now) {
    if (this.disposed) return;
    const dt = this.previous ? Math.min((now - this.previous) / 1000, .05) : 1 / 60;
    this.previous = now;
    const bands = this.audio.sample(dt);
    this.time += dt * (this.reducedMotion.matches ? .22 : 1 + bands.level*.6);
    for (let i = 0; i < 2; i++) this.pointer[i] += (this.targetPointer[i]-this.pointer[i])*(1-Math.exp(-dt*3));
    const gl = this.gl;
    gl.disable(gl.BLEND);
    this.draw(this.ring, this.quad, 'position', 2, gl.TRIANGLES, 6, bands);
    gl.enable(gl.BLEND);
    gl.blendFunc(gl.SRC_ALPHA, gl.ONE);
    this.draw(this.particles, this.points, 'seed', 3, gl.POINTS, this.count, bands);
    this.frames++;
    this.frame = requestAnimationFrame(this.render);
  }

  dispose() {
    this.disposed = true;
    cancelAnimationFrame(this.frame);
    this.resizeObserver.disconnect();
    this.canvas.removeEventListener('pointermove', this.move);
    this.canvas.removeEventListener('pointerleave', this.leave);
    this.canvas.removeEventListener('webglcontextlost', this.lost);
    this.canvas.removeEventListener('webglcontextrestored', this.restored);
    document.removeEventListener('visibilitychange', this.visibility);
    this.gl.deleteBuffer(this.quad);
    this.gl.deleteBuffer(this.points);
    this.gl.deleteProgram(this.ring.program);
    this.gl.deleteProgram(this.particles.program);
  }
}
