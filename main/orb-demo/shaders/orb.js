export const quadVertex = `
attribute vec2 position;
varying vec2 uv;
void main() { uv = position; gl_Position = vec4(position, 0., 1.); }
`;

export const ringFragment = `
precision highp float;
varying vec2 uv;
uniform float time;
uniform vec4 audio;
uniform vec2 pointer;
const float PI = 3.14159265;
vec3 palette(float a) {
  // Clockwise from the right: violet, pink, cyan, white, magenta, amber, white.
  float t = fract(a / (2. * PI) + 1.);
  if (t < .14) return mix(vec3(.38,.04,1.), vec3(.92,.02,1.), t/.14);
  if (t < .25) return mix(vec3(.92,.02,1.), vec3(.55,.02,1.), (t-.14)/.11);
  if (t < .34) return mix(vec3(.55,.02,1.), vec3(.22,.8,1.), (t-.25)/.09);
  if (t < .42) return mix(vec3(.22,.8,1.), vec3(1.,.8,1.), (t-.34)/.08);
  if (t < .53) return mix(vec3(1.,.8,1.), vec3(1.,.04,.63), (t-.42)/.11);
  if (t < .68) return mix(vec3(1.,.04,.63), vec3(1.,.65,.10), (t-.53)/.15);
  if (t < .79) return mix(vec3(1.,.65,.10), vec3(1.,.72,.95), (t-.68)/.11);
  if (t < .93) return mix(vec3(1.,.72,.95), vec3(.5,.8,1.), (t-.79)/.14);
  return mix(vec3(.5,.8,1.), vec3(.38,.04,1.), (t-.93)/.07);
}
void main() {
  vec2 p = uv - pointer * .009;
  float r = length(p);
  float a = atan(-p.y, p.x);
  float radius = .638 + .0025*sin(time*.7) + audio.x*.017 + audio.w*.01;
  radius += audio.x*.007*sin(a*3.+time*1.7) + audio.y*.004*sin(a*7.-time*2.);
  float d = abs(r-radius);
  vec3 hue = palette(a + .018*sin(time*.25));
  float strength = .86 + audio.w*.65 + audio.y*.18;
  float width = .023 + audio.w*.005;
  float core = exp(-pow(d/width, 2.));
  float closeGlow = exp(-d/(.019+audio.w*.008));
  float bloom = exp(-d/(.055+audio.x*.025));
  float outer = exp(-pow((r-radius-.035)/.17,2.))*smoothstep(.56,.76,r);
  float hairs = pow(.5+.5*sin(a*1150.+sin(a*41.-time)*2.), 9.) * exp(-d/.029) * smoothstep(.009,.022,d);
  vec3 color = vec3(0.);
  color += vec3(.025,.018,.38)*outer*(.65+audio.w);
  color += hue * (closeGlow*.66 + bloom*.29 + hairs*.13) * strength;
  color += mix(hue,vec3(1.),.22)*core*1.35*strength;
  gl_FragColor = vec4(color,1.);
}
`;

export const particleVertex = `
precision highp float;
attribute vec3 seed;
uniform float time;
uniform float pixelRatio;
uniform float viewport;
uniform vec4 audio;
uniform vec2 pointer;
varying vec3 tint;
varying float opacity;
void main() {
  float u = seed.x;
  float v = seed.y;
  float layer = seed.z;
  float t = time*.29;
  // A stack of folded sheets occupying a sphere, projected with perspective.
  float x = u*.60;
  float envelope = sqrt(max(0.,1.-u*u));
  float fold = sin(u*4.1+t+layer*.8);
  float wave = sin(u*5.5-v*3.2+t*1.4+layer*.6);
  float y = v*envelope*.38 + fold*envelope*(.12+audio.x*.14);
  y += wave*envelope*(.035+audio.y*.10);
  float z = sin(v*3.1+u*2.3+t+layer*.7)*envelope*.29 + layer*.08;
  x += sin(v*6.+t*2.+layer)*audio.x*.025;
  y += sin(u*33.+v*21.+t*8.+layer*4.)*audio.z*.014;
  z += cos(v*27.-u*20.+t*6.)*audio.z*.02;
  float angle = .16*sin(t*.6)+pointer.x*.10;
  vec3 p = vec3(x*cos(angle)+z*sin(angle),y,z*cos(angle)-x*sin(angle));
  p.y += pointer.y*p.z*.10;
  float perspective = 1.65/(1.65-p.z);
  vec2 screen = p.xy*perspective;
  float edge = 1.-smoothstep(.565,.624,length(screen));
  float depth = smoothstep(-.48,.4,p.z);
  float ribbon = pow(.5+.5*sin(v*4.8+u*3.+t+layer),3.);
  // Dark gaps keep the interior airy; the dominant wave sits left of center.
  float left = 1.-smoothstep(-.25,.47,screen.x);
  opacity = edge*(.045 + .46*ribbon)*(.25+.75*depth)*(.24+.76*left);
  opacity *= 2.4 + audio.w*1.4 + audio.y*.8;
  tint = mix(vec3(.18,.29,.95),vec3(.78,.12,.87),ribbon*.8+layer*.08);
  tint = mix(tint,vec3(.64,.70,1.),depth*.22);
  gl_Position = vec4(screen,0.,1.);
  gl_PointSize = clamp((1.15+depth*1.8+audio.z*.6)*pixelRatio*viewport/680., 1., 5.5);
}
`;

export const particleFragment = `
precision mediump float;
varying vec3 tint;
varying float opacity;
void main() {
  float d = length(gl_PointCoord-.5)*2.;
  if (d>1.) discard;
  float light = exp(-d*d*3.5);
  gl_FragColor = vec4(tint,opacity*light);
}
`;
