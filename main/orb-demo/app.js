import { AudioInput } from './utils/audio.js';
import { Orb } from './components/orb.js';

const button = document.querySelector('#audio');
const simulateButton = document.querySelector('#simulate');
const status = document.querySelector('#status');
const audio = new AudioInput();
let orb;
let active = false;

function setStatus(message, enabled = false) {
  status.querySelector('span').textContent = message;
  status.classList.toggle('active', enabled);
  button.setAttribute('aria-pressed', String(enabled));
  button.querySelector('span').textContent = enabled ? 'Stop Audio' : 'Start Audio';
  simulateButton.setAttribute('aria-pressed', String(audio.simulating));
  simulateButton.querySelector('span').textContent = audio.simulating ? 'Stop Simulation' : 'Simulate Audio';
  status.classList.toggle('active', enabled || audio.simulating);
}

async function stop() {
  active = false;
  await audio.stop();
  setStatus('Idle · microphone off');
}

async function toggle() {
  button.disabled = true;
  simulateButton.disabled = true;
  try {
    if (active) await stop();
    else {
      if (audio.simulating) await stop();
      setStatus('Waiting for microphone permission…');
      active = await audio.start();
      if (active) setStatus('Listening · microphone active', true);
    }
  } catch (error) {
    const messages = {
      NotAllowedError: 'Microphone permission denied. Allow access in your browser and try again.',
      NotFoundError: 'No microphone found. Connect one and try again.',
      NotReadableError: 'Microphone unavailable. Check whether another app is using it.',
    };
    active = false;
    setStatus(messages[error.name] || error.message);
  } finally {
    button.disabled = false;
    simulateButton.disabled = false;
  }
}

async function toggleSimulation() {
  button.disabled = simulateButton.disabled = true;
  try {
    const wasSimulating = audio.simulating;
    await stop();
    if (!wasSimulating) {
      audio.startSimulation();
      setStatus('Simulating audio · microphone off');
    }
  } finally {
    button.disabled = simulateButton.disabled = false;
  }
}

try {
  orb = new Orb(document.querySelector('#orb'), audio);
  button.addEventListener('click', toggle);
  simulateButton.addEventListener('click', toggleSimulation);
  audio.onEnded = stop;
} catch (error) {
  setStatus(error.message);
  button.disabled = true;
  simulateButton.disabled = true;
}

window.addEventListener('pagehide', () => {
  void audio.stop();
  orb?.dispose();
  button.removeEventListener('click', toggle);
  simulateButton.removeEventListener('click', toggleSimulation);
});
// Recreate resources when restoring a page from the browser's back/forward cache.
window.addEventListener('pageshow', event => { if (event.persisted) location.reload(); });

// Read-only diagnostics for performance checks; never exposes microphone samples.
Object.defineProperty(window, '__orbDiagnostics', {
  get: () => ({ frames: orb?.frames || 0, particles: orb?.count || 0, bands: { ...audio.bands }, active, simulating: audio.simulating, contextState: audio.context?.state || 'closed' }),
});
