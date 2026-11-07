import * as THREE from './vendor/three/three.module.js';

const deformation = `
uniform float waterTime;
uniform float waterEnergy;
uniform float waterActivity;
uniform float waterAssistant;
float hash31(vec3 p){p=fract(p*.1031);p+=dot(p,p.yzx+33.33);return fract((p.x+p.y)*p.z);}
float noise3(vec3 p){
 vec3 i=floor(p),f=fract(p);f=f*f*(3.-2.*f);
 return mix(mix(mix(hash31(i),hash31(i+vec3(1,0,0)),f.x),mix(hash31(i+vec3(0,1,0)),hash31(i+vec3(1,1,0)),f.x),f.y),
 mix(mix(hash31(i+vec3(0,0,1)),hash31(i+vec3(1,0,1)),f.x),mix(hash31(i+vec3(0,1,1)),hash31(i+vec3(1,1,1)),f.x),f.y),f.z);
}
vec3 waterPosition(vec3 p){
 float t=waterTime;
 if(waterAssistant>.5){
  float softness=noise3(p*1.6+vec3(t*.13,-t*.09,t*.11))-.5;
  float breathing=noise3(p*2.8+vec3(-t*.08,t*.12,t*.06))-.5;
  vec3 q=p*(1.+softness*(.085+waterEnergy*.055)+breathing*.025);
  q.x*=1.+.035*sin(t*.39+1.2);
  q.y*=1.035+.025*sin(t*.27);
  q.z*=.98+.025*cos(t*.31);
  q.x+=.028*sin(p.y*2.4+t*.33)*p.y;
  q.z+=.018*sin(p.x*2.1-t*.26)*p.y;
  return q;
 }
 float angle=waterActivity*.18*sin(t*.45);
 vec3 flow=vec3(cos(angle)*p.x-sin(angle)*p.z,p.y,sin(angle)*p.x+cos(angle)*p.z);
 float n=noise3(flow*2.1+vec3(t*.12,-t*.16,t*.09))-.5;
 float wave=sin(p.y*8.-t*1.8+noise3(p*1.7)*2.);
 float radius=1.+.036*n+(.002+waterEnergy*.022)*wave;
 vec3 q=p*radius;
 q.x*=1.+.024*sin(t*.31)+.012*p.y;
 q.y*=1.035+.012*sin(t*.27+1.);
 q.z*=.98;
 q.x+=.015*sin(p.y*2.+t*.23)*p.y;
 return q;
}
`;

function studioEnvironment(renderer) {
 const studio=new THREE.Scene();studio.background=new THREE.Color('#25323b');
 const panels=[];
 const panel=(width,height,position,color,intensity)=>{
  const material=new THREE.MeshBasicMaterial({color:new THREE.Color(color).multiplyScalar(intensity),side:THREE.DoubleSide});
  const mesh=new THREE.Mesh(new THREE.PlaneGeometry(width,height),material);
  mesh.position.set(...position);mesh.lookAt(0,0,0);studio.add(mesh);panels.push(mesh);
 };
 panel(3.5,2,[-3,3,4],'#ffffff',3.5);
 panel(1.2,4,[4,1,-2],'#d6efff',2);
 panel(2,4,[4,.5,4],'#98b8c5',.6);
 panel(5,3,[0,-4,1],'#253a42',.6);
 panel(2.8,3.5,[-4,-.5,-1],'#30414a',.6);
 panel(2,1.4,[1,4,-4],'#e5f4f6',1.3);
 const generator=new THREE.PMREMGenerator(renderer);
 const target=generator.fromScene(studio,.065,.1,30);
 generator.dispose();panels.forEach(mesh=>{mesh.geometry.dispose();mesh.material.dispose()});
 return target;
}

function backdrop() {
 const material=new THREE.ShaderMaterial({
  vertexShader:'varying vec2 positionXY;void main(){positionXY=position.xy;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}',
  fragmentShader:`varying vec2 positionXY;
  void main(){
   vec2 p=positionXY;
   vec3 color=vec3(.56,.64,.68);
   color+=.065*exp(-dot(p-vec2(-2.,2.),p-vec2(-2.,2.))*.08);
   float sweep=exp(-pow((p.x+.52*p.y+.5)*1.3,2.));
   color-=vec3(.24,.23,.21)*sweep;
   float light=exp(-pow((p.x+.52*p.y-1.7)*1.1,2.));
   color+=vec3(.045,.05,.05)*light;
   float horizon=p.y+.28*p.x+.65;
   color-=vec3(.23,.23,.22)*exp(-horizon*horizon*24.);
   color+=vec3(.11,.12,.13)*exp(-pow(horizon-.22,2.)*32.);
   gl_FragColor=vec4(color,1.);
   #include <tonemapping_fragment>
   #include <colorspace_fragment>
  }`
 });
 const mesh=new THREE.Mesh(new THREE.PlaneGeometry(40,30),material);mesh.position.z=-3;return mesh;
}

// Agent 使用柔和的多色摄影棚光，语音水滴继续使用原有环境。
function assistantEnvironment(renderer){
 const studio=new THREE.Scene();studio.background=new THREE.Color('#314d49');
 const panels=[];
 for(const [color,position,size,intensity] of [
  ['#e5ebe3',[-3,3,4],[3.5,2],3.2],['#d5e4ed',[4,2,-2],[1.2,4],2.1],
  ['#b6adbf',[-3,-1,-4],[3,4],.8],['#d6c5a8',[3,-3,3],[4,3],.65],
  ['#ffffff',[-2,1.5,4],[.4,3.5],3.4],['#445f5a',[1,-4,2],[5,3],.5],
 ]){
  const material=new THREE.MeshBasicMaterial({color:new THREE.Color(color).multiplyScalar(intensity),side:THREE.DoubleSide});
  const mesh=new THREE.Mesh(new THREE.PlaneGeometry(...size),material);mesh.position.set(...position);mesh.lookAt(0,0,0);studio.add(mesh);panels.push(mesh);
 }
 const generator=new THREE.PMREMGenerator(renderer),target=generator.fromScene(studio,.08,.1,30);
 generator.dispose();panels.forEach(mesh=>{mesh.geometry.dispose();mesh.material.dispose();});return target;
}

function assistantBackdrop(){
 // Three.js 的 transmission 预渲染读取不透明队列；保留片元 alpha 给画布合成。
 const material=new THREE.ShaderMaterial({transparent:false,depthWrite:false,
  vertexShader:'varying vec2 positionXY;void main(){positionXY=position.xy;gl_Position=projectionMatrix*modelViewMatrix*vec4(position,1.);}',
  fragmentShader:`varying vec2 positionXY;
  void main(){
   vec2 p=positionXY;
   vec3 color=vec3(.48,.66,.55);
   float blue=exp(-dot(p-vec2(1.2,.8),p-vec2(1.2,.8))*.7);
   float violet=exp(-dot(p-vec2(-1.1,-.5),p-vec2(-1.1,-.5))*.8);
   float amber=exp(-dot(p-vec2(.5,-1.2),p-vec2(.5,-1.2))*.8);
   color=mix(color,vec3(.50,.65,.82),blue*.85);
   color=mix(color,vec3(.66,.55,.76),violet*.8);
   color=mix(color,vec3(.90,.76,.55),amber*.8);
   color+=vec3(.14)*exp(-pow(p.x*.7+p.y*.5+.25,2.)*3.);
   color-=vec3(.12,.10,.09)*exp(-pow(p.x*.8-p.y*.4-.8,2.)*5.);
   float horizon=p.y+.28*p.x+.65;
   color-=vec3(.22,.19,.16)*exp(-horizon*horizon*24.);
   color+=vec3(.12,.13,.12)*exp(-pow(horizon-.22,2.)*32.);
   float alpha=(1.-smoothstep(.8,3.2,length(p)))*.65;
   gl_FragColor=vec4(color,alpha);
   #include <tonemapping_fragment>
   #include <colorspace_fragment>
   gl_FragColor.rgb*=gl_FragColor.a;
  }`});
 const mesh=new THREE.Mesh(new THREE.PlaneGeometry(40,30),material);mesh.position.z=-3;return mesh;
}

// 用两次 Snell 折射计算光束在承接平面的聚集；近球体用于低成本焦散近似。
function caustics(uniforms,mobile) {
 const count=mobile?2048:4096,positions=new Float32Array(count*3);
 const golden=Math.PI*(3-Math.sqrt(5));
 for(let i=0;i<count;i++){const r=Math.sqrt((i+.5)/count)*.97;positions[i*3]=Math.cos(i*golden)*r;positions[i*3+1]=Math.sin(i*golden)*r;}
 const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.BufferAttribute(positions,3));
 const material=new THREE.ShaderMaterial({uniforms,transparent:true,depthWrite:false,blending:THREE.AdditiveBlending,
  vertexShader:`uniform float waterTime;uniform float waterEnergy;varying float strength;
  void main(){
   vec2 disk=position.xy;
   vec3 entry=vec3(disk.x,sqrt(max(.001,1.-dot(disk,disk))),disk.y);
   vec3 inside=refract(vec3(0,-1,0),normalize(entry),1./1.333);
   vec3 exitPoint=entry+inside*(-2.*dot(entry,inside));
   vec3 outside=refract(inside,-normalize(exitPoint),1.333);
   float distance=(-1.48-exitPoint.y)/min(-.001,outside.y);
   vec3 hit=exitPoint+outside*distance;
   hit.x+=.012*sin(waterTime*.6+disk.y*5.);
   hit.z+=.012*cos(waterTime*.5+disk.x*5.);
   strength=.0025*(1.+waterEnergy*.2);
   gl_Position=projectionMatrix*modelViewMatrix*vec4(hit,1.);gl_PointSize=8.;
  }`,
  fragmentShader:`varying float strength;void main(){float d=length(gl_PointCoord-.5);float a=exp(-d*d*22.)*strength;gl_FragColor=vec4(.65,.85,.9,a);}`
 });
 const points=new THREE.Points(geometry,material);points.frustumCulled=false;return points;
}

export class WaterOrb {
 constructor(host,options={}) {
  this.host=host;this.mode='idle';this.volume=0;this.energy=0;this.elapsed=0;this.last=0;this.disposed=false;
  this.assistant=options.appearance==='assistant';
  this.reduced=matchMedia('(prefers-reduced-motion: reduce)');
  const mobile=host.clientWidth<600;
  this.renderer=new THREE.WebGLRenderer({antialias:true,alpha:true,powerPreference:'low-power'});
  this.renderer.setPixelRatio(Math.min(devicePixelRatio,mobile?1.5:1.75));
  this.renderer.toneMapping=THREE.ACESFilmicToneMapping;this.renderer.toneMappingExposure=1.1;
  if(this.assistant)this.renderer.toneMappingExposure=1.08;
  this.renderer.outputColorSpace=THREE.SRGBColorSpace;
  this.renderer.transmissionResolutionScale=mobile?.65:.85;
  const canvas=this.renderer.domElement;canvas.className='water-canvas';canvas.setAttribute('aria-hidden','true');host.replaceChildren(canvas);
  this.scene=new THREE.Scene();this.camera=new THREE.PerspectiveCamera(35,1,.1,50);this.camera.position.set(0,.3,5.3);this.camera.lookAt(0,-.03,0);
  this.environment=this.assistant?assistantEnvironment(this.renderer):studioEnvironment(this.renderer);this.scene.environment=this.environment.texture;
  this.uniforms={waterTime:{value:0},waterEnergy:{value:0},waterActivity:{value:0},waterAssistant:{value:this.assistant?1:0}};
  this.material=new THREE.MeshPhysicalMaterial({color:0xffffff,metalness:0,roughness:.025,transmission:1,ior:1.333,thickness:2.5,attenuationColor:new THREE.Color('#e8faf8'),attenuationDistance:24,clearcoat:1,clearcoatRoughness:.035,dispersion:.025,envMapIntensity:1.25,side:THREE.FrontSide});
  if(this.assistant){this.material.roughness=.025;this.material.clearcoatRoughness=.035;this.material.envMapIntensity=1.4;this.material.transparent=true;this.material.opacity=.82;this.material.attenuationColor.set('#eef5ef');this.material.attenuationDistance=30;this.material.dispersion=.012;}
  this.material.onBeforeCompile=shader=>{
   Object.assign(shader.uniforms,this.uniforms);shader.vertexShader=deformation+shader.vertexShader;
   shader.vertexShader=shader.vertexShader.replace('#include <beginnormal_vertex>',`
    vec3 radial=normalize(position);
    vec3 tangent=normalize(cross(abs(radial.y)>.95?vec3(1,0,0):vec3(0,1,0),radial));
    vec3 bitangent=normalize(cross(radial,tangent));
    vec3 surface=waterPosition(position);
    vec3 du=waterPosition(normalize(position+tangent*.003))-surface;
    vec3 dv=waterPosition(normalize(position+bitangent*.003))-surface;
    vec3 objectNormal=normalize(cross(du,dv));
   `).replace('#include <begin_vertex>','vec3 transformed=waterPosition(position);');
   // 显式计算入水、出水两次折射，将出射光线投影到真实背景平面。
   shader.fragmentShader=shader.fragmentShader.replace('#include <transmission_fragment>',`
    material.transmission=transmission;material.transmissionAlpha=1.;
    vec3 waterN=inverseTransformDirection(normal,viewMatrix);
    vec3 waterV=normalize(cameraPosition-vWorldPosition);
    vec3 center=modelMatrix[3].xyz;
    vec3 localEntry=vWorldPosition-center;
    vec3 resultLight=vec3(0.);
    float travel=0.;
    for(int channel=0;channel<3;channel++){
     float index=ior+(float(channel)-1.)*.00035;
     vec3 ray=refract(-waterV,waterN,1./index);
     vec3 shape=vec3(1.,1.035,.98);
     vec3 ep=localEntry/shape,rd=ray/shape;
     float b=dot(ep,rd),a=dot(rd,rd);
     float distance=max(.001,(-b+sqrt(max(0.,b*b-a*(dot(ep,ep)-1.))))/a);
     vec3 exitPoint=vWorldPosition+ray*distance;
     vec3 exitNormal=normalize((exitPoint-center)/(shape*shape));
     vec3 outgoing=refract(ray,-exitNormal,index);
     float reach=(-3.-exitPoint.z)/min(-.02,outgoing.z);
     vec3 hit=exitPoint+outgoing*max(0.,reach);
     vec4 projected=projectionMatrix*viewMatrix*vec4(hit,1.);
     vec2 uv=clamp(projected.xy/projected.w*.5+.5,vec2(.002),vec2(.998));
     resultLight[channel]=textureLod(transmissionSamplerMap,uv,0.)[channel];
     travel=distance;
    }
    vec3 absorption=volumeAttenuation(travel,attenuationColor,attenuationDistance);
    vec3 fresnel=EnvironmentBRDF(waterN,waterV,material.specularColor,material.specularF90,material.roughness);
    totalDiffuse=(1.-fresnel)*resultLight*absorption;
   `);
  };
  this.orb=new THREE.Mesh(new THREE.SphereGeometry(1,mobile?64:96,mobile?40:64),this.material);
  if(this.assistant)this.scene.add(assistantBackdrop(),this.orb);
  else this.scene.add(backdrop(),this.orb,caustics(this.uniforms,mobile));
  const fill=new THREE.DirectionalLight('#d4ecff',.12);fill.position.set(-3,4,3);this.scene.add(fill);
  this.resize=()=>{if(this.disposed)return;const w=host.clientWidth,h=host.clientHeight;if(!w||!h)return;this.renderer.setSize(w,h,false);this.camera.aspect=w/h;this.camera.updateProjectionMatrix();if(this.assistant&&(this.reduced.matches||this.mode==='error')&&!document.hidden)this.render(performance.now())};
  this.observer=new ResizeObserver(this.resize);this.observer.observe(host);this.resize();
  this.contextLost=event=>{
   event.preventDefault();this.host.dataset.render='error';
   if(this.assistant){this.contextUnavailable=true;this.mode='error';this.host.dataset.mode='error';this.volume=0;this.energy=0;this.uniforms.waterEnergy.value=0;this.uniforms.waterActivity.value=0;}
   this.host.dispatchEvent(new CustomEvent('water-error',{detail:this.assistant?'智能助手三维渲染已中断，请重新打开助手':'三维渲染已中断，请关闭语音窗口后重新打开'}));cancelAnimationFrame(this.frame);
  };
  canvas.addEventListener('webglcontextlost',this.contextLost);
  this.visibility=()=>{cancelAnimationFrame(this.frame);if(!document.hidden&&!this.disposed){this.last=0;this.frame=requestAnimationFrame(time=>this.render(time))}};
  document.addEventListener('visibilitychange',this.visibility);
  this.motionChange=()=>{if(!this.assistant||this.disposed||this.contextUnavailable)return;cancelAnimationFrame(this.frame);this.last=0;if(!document.hidden)this.frame=requestAnimationFrame(time=>this.render(time));};
  if(this.assistant)this.reduced.addEventListener('change',this.motionChange);
  this.frame=requestAnimationFrame(time=>this.render(time));
 }
 setMode(mode){
  this.mode=mode;this.host.dataset.mode=mode;
  if(this.assistant){
   if(mode==='error'){this.volume=0;this.energy=0;this.uniforms.waterEnergy.value=0;this.uniforms.waterActivity.value=0;}
   this.motionChange();
  }
 }
 setVolume(value){this.volume=this.assistant&&this.mode==='error'?0:Math.max(0,Math.min(1,Number.isFinite(value)?value:0))}
 render(time) {
  if(this.disposed||document.hidden||this.assistant&&this.contextUnavailable)return;
  const dt=this.last?Math.min(.05,(time-this.last)/1000):0;this.last=time;
  const target=['listening','speaking'].includes(this.mode)?this.volume:0;
  this.energy+=(target-this.energy)*(1-Math.exp(-dt*7));
  const speed=this.assistant?(this.mode==='thinking'?.44:this.mode==='listening'?.33:.22):(this.mode==='thinking'?1.4:this.mode==='listening'?1.05:.65);
  if(!this.reduced.matches&&!(this.assistant&&this.mode==='error'))this.elapsed+=dt*speed;
  this.uniforms.waterTime.value=this.elapsed;
  this.uniforms.waterEnergy.value=this.reduced.matches?0:this.energy;
  const activity=this.mode==='thinking'?1:this.mode==='listening'?.4:this.mode==='speaking'?.6:0;
  this.uniforms.waterActivity.value+=(activity-this.uniforms.waterActivity.value)*(1-Math.exp(-dt*3));
  this.orb.position.y=this.reduced.matches?0:Math.sin(this.elapsed*.55)*.035;
  this.orb.rotation.y=this.reduced.matches?0:Math.sin(this.elapsed*.12)*.1;
  this.orb.scale.setScalar(1+(this.reduced.matches?0:Math.sin(this.elapsed*.65)*.003));
  this.renderer.render(this.scene,this.camera);this.host.dataset.render='ready';
  if(!this.assistant||!this.reduced.matches&&this.mode!=='error')this.frame=requestAnimationFrame(next=>this.render(next));
 }
 dispose(){
  if(this.disposed)return;this.disposed=true;cancelAnimationFrame(this.frame);this.observer.disconnect();document.removeEventListener('visibilitychange',this.visibility);
  if(this.assistant)this.reduced.removeEventListener('change',this.motionChange);
  this.renderer.domElement.removeEventListener('webglcontextlost',this.contextLost);
  this.scene.traverse(object=>{object.geometry?.dispose();if(object.material)object.material.dispose()});
  this.environment.dispose();this.renderer.dispose();this.renderer.forceContextLoss();this.host.replaceChildren();
 }
}
