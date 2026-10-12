# Audio reactive orb — isolated demo

A procedural neon ring and 27,648 GPU-animated particles, inspired by the supplied reference. Built with native WebGL and Web Audio; no runtime packages, frameworks, remote assets, or paid services. Everything for this experiment stays in `orb-demo/`.

## Run

Requires Node.js 18+.

```powershell
cd orb-demo
npm run dev
```

Open **http://localhost:5174**. Click **Start Audio**, allow microphone access, and speak or play sound near the microphone. **Stop Audio** releases the device and closes the audio context. Pointer movement adds gentle depth parallax. The orb animates while idle. Microphone capture requires localhost or HTTPS; opening the HTML as a local file is not supported.

Without a microphone, click **Simulate Audio**. It supplies varying bass beats, mid-frequency phrases, and high-frequency detail to the same animation controls, without requesting microphone permission or playing sound. **Stop Simulation** smoothly returns the orb to idle. Switching modes releases the previous input automatically.

Audio is processed locally and never recorded, uploaded, or played back. Permission denial, missing devices, and disconnected microphones have visible status messages. Microphone input does not automatically capture system audio; use speakers near the microphone for music.

## How it works

- A separate fragment shader draws the neon gradient, bright core, fine fringe, and broad glow.
- Three folded particle sheets occupy depth inside the sphere; perspective, layered flow, and soft points create a volumetric wave while leaving black negative space.
- A 2048-point FFT separates bass (30–250 Hz), mids (250–2500 Hz), and highs (2500–12000 Hz). Bass drives deeper displacement and expansion, mids drive the folds and particle intensity, and highs drive fine turbulence and point size. RMS loudness controls bloom and energy.
- Exponential attack/release smoothing avoids abrupt jumps. Rendering stays inside requestAnimationFrame with GPU particle deformation. Device pixel ratio is capped at 2, and rendering pauses in background tabs. Reduced-motion preferences slow the animation.
- Page teardown releases microphone tracks, audio nodes/context, GPU resources, listeners, and animation frames. WebGL context restoration rebuilds GPU resources.

## Browser checks

Only test tooling needs installation (the dev server has no dependencies):

```powershell
npm install
npx playwright install chromium
npm test
```

Playwright checks rendering, desktop/mobile layout, microphone start/stop/restart with a synthetic PCM microphone, permission denial, frequency separation, and smooth release. Screenshots go to `test-results/`. Test audio is generated locally in `.cache/`. Synthetic input verifies the browser audio pipeline; actual hardware permission prompts and performance should also be checked on the intended device. 60 FPS is a target, not a guarantee on all GPUs.

`window.__orbDiagnostics` provides read-only frame counts, particle counts, and aggregate audio bands for inspection. It exposes no raw audio.

No existing application files, routes, Python dependencies, or frontend setup are modified.
