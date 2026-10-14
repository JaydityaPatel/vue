import { useEffect, useMemo } from 'react';
import { Canvas, useFrame, useThree } from '@react-three/fiber';
import { AdditiveBlending, Vector2, Vector4 } from 'three';
import { quad, seeds } from './geometry';
import { particleFragment, particleVertex, quadVertex, ringFragment } from './shaders';
import { startOrbLoop } from './loop';

export type OrbState = 'idle' | 'listening' | 'thinking' | 'speaking';
export interface OrbProps {
  orbState: OrbState;
  audioLevel: number;
  size?: number | string;
  sttActive?: boolean;
}

export function orbAppearance(state: OrbState) {
  return { brightness: { idle: .65, listening: 1, thinking: .85, speaking: 1.15 }[state],
    speed: { idle: .45, listening: 1, thinking: 2.8, speaking: 1 }[state] };
}

function Scene({ orbState, audioLevel, sttActive }: OrbProps) {
  const { advance, size, gl } = useThree();
  const uniforms = useMemo(() => ({ time: { value: 0 }, audio: { value: new Vector4() },
    pointer: { value: new Vector2() }, pixelRatio: { value: 1 }, viewport: { value: 680 },
    brightness: { value: 1 } }), []);
  useEffect(() => startOrbLoop(advance, !!sttActive), [advance, sttActive]);
  useFrame((state, delta) => {
    const reduced = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    const appearance = orbAppearance(orbState);
    uniforms.time.value += Math.min(delta, .15) * appearance.speed * (reduced ? .22 : 1);
    // Browser TTS exposes playback events, not PCM. Only mic samples drive deformation.
    const amplitude = orbState === 'listening' ? audioLevel : 0;
    uniforms.audio.value.lerp(new Vector4(amplitude, amplitude * .7, amplitude * .3, amplitude), .25);
    uniforms.brightness.value = appearance.brightness;
    uniforms.pointer.value.lerp(state.pointer, .08);
    uniforms.viewport.value = Math.min(size.width, size.height);
    uniforms.pixelRatio.value = gl.getPixelRatio();
  });
  return <>
    <mesh frustumCulled={false} renderOrder={0}>
      <bufferGeometry><bufferAttribute attach="attributes-position" args={[quad, 3]}/></bufferGeometry>
      <rawShaderMaterial vertexShader={quadVertex} fragmentShader={ringFragment} uniforms={uniforms}
        depthTest={false} depthWrite={false} toneMapped={false}/>
    </mesh>
    <points frustumCulled={false} renderOrder={1}>
      <bufferGeometry drawRange={{ start: 0, count: sttActive ? seeds.length / 9 : seeds.length / 3 }}>
        <bufferAttribute attach="attributes-position" args={[seeds, 3]}/>
        <bufferAttribute attach="attributes-seed" args={[seeds, 3]}/>
      </bufferGeometry>
      <rawShaderMaterial vertexShader={particleVertex} fragmentShader={particleFragment} uniforms={uniforms}
        transparent blending={AdditiveBlending} depthTest={false} depthWrite={false} toneMapped={false}/>
    </points>
  </>;
}

export default function Orb({ size = '100%', audioLevel, ...props }: OrbProps) {
  const level = Number.isFinite(audioLevel) ? Math.min(1, Math.max(0, audioLevel)) : 0;
  return <div className={`voice-orb orb-${props.orbState}`} data-state={props.orbState}
    data-audio-level={level} aria-label={`Vue is ${props.orbState}`} role="img"
    style={{ width: size, maxWidth: '100%', aspectRatio: '1' }}>
    <Canvas frameloop="never" dpr={props.sttActive ? 1 : [1, 1.5]}
      gl={{ antialias: false, alpha: false, powerPreference: 'low-power' }}>
      <Scene {...props} audioLevel={level}/>
    </Canvas>
  </div>;
}
