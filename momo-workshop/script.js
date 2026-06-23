'use strict';

const $ = (id) => document.getElementById(id);
const canvas = $('editorCanvas');
const ctx = canvas.getContext('2d');

const COLORS_FILL = ['#ffffff','#111111','#ef4444','#f97316','#facc15','#22c55e','#06b6d4','#3b82f6','#a855f7'];
const COLORS_STROKE = ['#111111','#ffffff','#dc2626','#ea580c','#ca8a04','#16a34a','#0891b2','#2563eb','#9333ea'];
const quickWords = ['这题我真的会了','我裂开了','先别急','已老实，求放过','你最好是','尊嘟假嘟','不愧是我','这合理吗'];
const filterDefs = {
  原图: { brightness: 100, contrast: 100, saturate: 100, hue: 0, sepia: 0, grayscale: 0 },
  清透: { brightness: 108, contrast: 96, saturate: 112, hue: 0, sepia: 0, grayscale: 0 },
  胶片: { brightness: 102, contrast: 112, saturate: 90, hue: -6, sepia: 18, grayscale: 0 },
  复古: { brightness: 98, contrast: 108, saturate: 78, hue: 8, sepia: 35, grayscale: 0 },
  奶油: { brightness: 112, contrast: 90, saturate: 88, hue: 6, sepia: 10, grayscale: 0 },
  冷白皮: { brightness: 114, contrast: 102, saturate: 92, hue: -12, sepia: 0, grayscale: 0 },
  暖阳: { brightness: 108, contrast: 105, saturate: 118, hue: 10, sepia: 12, grayscale: 0 },
  黑白: { brightness: 102, contrast: 112, saturate: 100, hue: 0, sepia: 0, grayscale: 100 },
  高对比: { brightness: 100, contrast: 135, saturate: 115, hue: 0, sepia: 0, grayscale: 0 },
  暗调: { brightness: 78, contrast: 118, saturate: 88, hue: 0, sepia: 5, grayscale: 0 }
};
const adjustMeta = [
  ['brightness','亮度',50,150,100],['contrast','对比度',50,160,100],['saturate','饱和度',0,200,100],
  ['exposure','曝光',-50,50,0],['blur','模糊',0,10,0],['temperature','色温',-50,50,0],['vignette','暗角',0,80,0]
];

let state = {
  outputWidth: 800, outputHeight: 800, fitMode: 'cover', backgroundType: 'template', templateId: 'smile', imageDataUrl: '', backgroundFlipX: false, backgroundFlipY: false,
  layers: [], selectedLayerId: null, filter: '原图', adjustments: {}, exportFormat: 'png', jpgQuality: .92, filePrefix: 'meme-workshop', cropMode: false,
  cropRatio: 'free', cropRect: { x: 80, y: 80, w: 640, h: 640 }
};
adjustMeta.forEach(([k,,,,d]) => state.adjustments[k] = d);
let templates = [], stickers = [], bgImage = null, layerImageCache = new Map(), undoStack = [], redoStack = [], saveTimer = null;
let interaction = { mode: null, layerId: null, start: null, original: null, control: null };
let currentFinalDataUrl = '';

function initApp(){
  templates = createTemplates(); stickers = createStickers();
  renderTemplates(); renderStickers(); renderQuickTexts(); renderFilters(); renderAdjustments(); renderPalettes(); bindEvents();
  loadTemplate('smile', false);
  addTextLayer('这题我真的会了', state.outputWidth/2, state.outputHeight*.78, false);
  syncUI(); drawCanvas(); saveHistory(true); renderGallery();
}

function createCanvas(w=800,h=800){const c=document.createElement('canvas');c.width=w;c.height=h;return c;}
function makeTemplate(id,name,draw){const c=createCanvas(); const x=c.getContext('2d'); draw(x,c.width,c.height); return {id,name,canvas:c,dataUrl:c.toDataURL('image/png')};}
function faceBase(x,w,h,bg='#fff4b8',face='#ffd84d'){x.fillStyle=bg;x.fillRect(0,0,w,h);x.beginPath();x.arc(w/2,h/2,w*.34,0,Math.PI*2);x.fillStyle=face;x.fill();x.lineWidth=14;x.strokeStyle='rgba(0,0,0,.14)';x.stroke();}
function createTemplates(){return [
  makeTemplate('smile','微笑',(x,w,h)=>{faceBase(x,w,h); x.fillStyle='#222'; x.beginPath();x.arc(310,330,28,0,Math.PI*2);x.arc(490,330,28,0,Math.PI*2);x.fill();x.lineWidth=18;x.lineCap='round';x.beginPath();x.arc(400,420,120,.1*Math.PI,.9*Math.PI);x.strokeStyle='#222';x.stroke();}),
  makeTemplate('crack','裂开',(x,w,h)=>{faceBase(x,w,h,'#fff0cc'); x.fillStyle='#222';x.fillRect(285,330,70,18);x.fillRect(445,330,70,18);x.lineWidth=12;x.strokeStyle='#333';x.beginPath();x.moveTo(390,210);x.lineTo(425,300);x.lineTo(378,384);x.lineTo(430,470);x.lineTo(380,585);x.stroke();}),
  makeTemplate('think','思考',(x,w,h)=>{faceBase(x,w,h,'#edf7ff');x.fillStyle='#222';x.fillRect(290,330,70,16);x.beginPath();x.arc(500,338,22,0,Math.PI*2);x.fill();x.lineWidth=16;x.beginPath();x.moveTo(315,470);x.quadraticCurveTo(410,500,500,455);x.stroke();x.fillStyle='#ffc86b';x.beginPath();x.ellipse(545,525,120,55,-.5,0,Math.PI*2);x.fill();}),
  makeTemplate('shock','震惊',(x,w,h)=>{faceBase(x,w,h,'#dbeafe','#ffe28a');x.fillStyle='#fff';x.beginPath();x.arc(310,330,55,0,Math.PI*2);x.arc(490,330,55,0,Math.PI*2);x.fill();x.fillStyle='#111';x.beginPath();x.arc(310,330,20,0,Math.PI*2);x.arc(490,330,20,0,Math.PI*2);x.fill();x.beginPath();x.ellipse(400,465,58,85,0,0,Math.PI*2);x.fill();}),
  makeTemplate('speechless','无语',(x,w,h)=>{faceBase(x,w,h,'#e5e7eb','#d1d5db');x.strokeStyle='#111';x.lineWidth=16;x.lineCap='round';x.beginPath();x.moveTo(270,335);x.lineTo(355,335);x.moveTo(445,335);x.lineTo(530,335);x.moveTo(310,465);x.lineTo(490,465);x.stroke();}),
  makeTemplate('proud','得意',(x,w,h)=>{faceBase(x,w,h,'#dcfce7','#fcd34d');x.strokeStyle='#111';x.lineWidth=14;x.lineCap='round';x.beginPath();x.moveTo(280,310);x.lineTo(360,340);x.moveTo(520,310);x.lineTo(440,340);x.stroke();x.beginPath();x.moveTo(330,455);x.quadraticCurveTo(440,530,530,420);x.stroke();}),
  makeTemplate('sad','委屈',(x,w,h)=>{faceBase(x,w,h,'#dff7ff','#ffe08a');x.fillStyle='#111';x.beginPath();x.arc(315,340,24,0,Math.PI*2);x.arc(485,340,24,0,Math.PI*2);x.fill();x.strokeStyle='#111';x.lineWidth=14;x.beginPath();x.arc(400,500,110,1.15*Math.PI,1.85*Math.PI);x.stroke();x.fillStyle='#60a5fa';x.beginPath();x.ellipse(535,410,28,55,-.15,0,Math.PI*2);x.fill();}),
  makeTemplate('angry','暴怒',(x,w,h)=>{faceBase(x,w,h,'#fee2e2','#ffbf4d');x.strokeStyle='#111';x.lineWidth=18;x.lineCap='round';x.beginPath();x.moveTo(260,300);x.lineTo(360,350);x.moveTo(540,300);x.lineTo(440,350);x.stroke();x.beginPath();x.moveTo(320,485);x.quadraticCurveTo(400,430,500,485);x.stroke();x.fillStyle='#ef4444';for(let i=0;i<5;i++){x.beginPath();x.moveTo(170+i*95,190);x.lineTo(210+i*95,105);x.lineTo(250+i*95,190);x.fill();}})
];}
function createStickers(){
  const items=[['heart','❤️'],['star','✨'],['crown','👑'],['bear','🧸'],['cat','🐱'],['flower','🌷'],['date','’22 06 28'],['pin','📍北京'],['hot','🔥HOT'],['cool','COOL'],['smile','😎'],['calendar','🗓️'],['cherry','🍒'],['clover','🍀'],['photo','🖼️'],['arrow','➜'],['wave','﹏﹏'],['cloud','☁️'],['like','👍'],['animal','🦫']];
  return items.map(([id,label])=>{const dataUrl=stickerToDataUrl(label);const img=new Image();img.src=dataUrl;return {id,label,dataUrl,img};});
}
function stickerToDataUrl(label){const c=createCanvas(180,180),x=c.getContext('2d');x.clearRect(0,0,180,180);x.textAlign='center';x.textBaseline='middle';x.font=label.length>4?'bold 34px Microsoft YaHei':'90px Apple Color Emoji,Segoe UI Emoji,Arial';x.lineWidth=8;x.strokeStyle='rgba(255,255,255,.8)';x.strokeText(label,90,90);x.fillStyle='#fff';if(label.includes('COOL')){x.fillStyle='#facc15';}x.fillText(label,90,90);return c.toDataURL('image/png');}

function renderTemplates(){const grid=$('templateGrid');grid.innerHTML='';templates.forEach(t=>{const b=document.createElement('button');b.className='template-card';b.innerHTML=`<img src="${t.dataUrl}" alt="${t.name}"><span>${t.name}</span>`;b.onclick=()=>{loadTemplate(t.id);};grid.appendChild(b);});}
function renderStickers(){
  const grid=$('stickerGrid');grid.innerHTML='';
  const addCard=(item, extra='')=>{const b=document.createElement('button');b.className='sticker-card';b.innerHTML=`<img src="${item.dataUrl}" alt="${item.label||item.name}"><span>${item.label||item.name}${extra}</span>`;b.onclick=()=>addStickerLayer({id:item.id,label:item.label||item.name,dataUrl:item.dataUrl});grid.appendChild(b);};
  const title=document.createElement('div');title.className='sticker-section-title';title.textContent='表情模板也可作为贴纸粘贴';grid.appendChild(title);
  templates.forEach(t=>addCard({id:'tpl_'+t.id,label:t.name,dataUrl:t.dataUrl},'贴纸'));
  const title2=document.createElement('div');title2.className='sticker-section-title';title2.textContent='小红书风格装饰贴纸';grid.appendChild(title2);
  stickers.forEach(s=>addCard(s));
}
function renderQuickTexts(){const box=$('quickTexts');box.innerHTML='';quickWords.forEach(w=>{const b=document.createElement('button');b.className='btn secondary';b.textContent=w;b.onclick=()=>{const layer=getSelectedTextLayer()||addTextLayer('',state.outputWidth/2,state.outputHeight*.72,false);layer.text=w;$('textInput').value=w;drawCanvas();debounceSaveHistory();renderLayers();};box.appendChild(b);});}
function renderFilters(){const box=$('filterList');box.innerHTML='';Object.keys(filterDefs).forEach(name=>{const b=document.createElement('button');b.className='filter-card';b.textContent=name;b.onclick=()=>{state.filter=name;drawCanvas();saveHistory();renderFilters();};if(state.filter===name)b.classList.add('active');box.appendChild(b);});}
function renderAdjustments(){const box=$('adjustControls');box.innerHTML='';adjustMeta.forEach(([key,label,min,max,def])=>{const wrap=document.createElement('label');wrap.className='range-row';wrap.innerHTML=`${label} <span id="${key}Val">${state.adjustments[key]}</span><input id="adj_${key}" type="range" min="${min}" max="${max}" value="${state.adjustments[key]}">`;box.appendChild(wrap);wrap.querySelector('input').oninput=e=>{state.adjustments[key]=Number(e.target.value);$(key+'Val').textContent=e.target.value;drawCanvas();debounceSaveHistory();};});}
function renderPalettes(){setupPalette('fillPalette',COLORS_FILL,'fillColor');setupPalette('strokePalette',COLORS_STROKE,'strokeColor');}
function setupPalette(containerId, colors, inputId){const box=$(containerId);box.innerHTML='';colors.forEach(c=>{const b=document.createElement('button');b.className='color-dot';b.style.background=c;b.onclick=()=>{const layer=getSelectedTextLayer(); if(layer){ if(inputId==='fillColor')layer.fillColor=c; else layer.strokeColor=c; $(inputId).value=c; syncUI(); drawCanvas(); saveHistory();}};box.appendChild(b);});}

function bindEvents(){
  $('tabs').onclick=e=>{const btn=e.target.closest('.tab');if(!btn)return;document.querySelectorAll('.tab,.tab-content').forEach(x=>x.classList.remove('active'));btn.classList.add('active');$('tab-'+btn.dataset.tab).classList.add('active');};
  $('imageInput').onchange=e=>handleUpload(e.target.files[0]); setupDragUpload();
  ['fitMode','exportFormat','filePrefix'].forEach(id=>$(id).onchange=e=>{state[id==='fitMode'?'fitMode':id]=e.target.value;drawCanvas();saveHistory();});
  $('textInput').oninput=e=>{const layer=getSelectedTextLayer()||addTextLayer('',state.outputWidth/2,state.outputHeight*.72,false);layer.text=e.target.value;drawCanvas();debounceSaveHistory();renderLayers();};
  ['fontFamily','fontWeight'].forEach(id=>$(id).onchange=e=>{const l=getSelectedTextLayer();if(l){l[id]=e.target.value;drawCanvas();saveHistory();}});
  [['fontSize','fontSizeVal'],['strokeWidth','strokeWidthVal'],['lineHeight','lineHeightVal'],['letterSpacing','letterSpacingVal']].forEach(([id,val])=>$(id).oninput=e=>{const l=getSelectedTextLayer();$(val).textContent=e.target.value;if(l){l[id]=Number(e.target.value);drawCanvas();debounceSaveHistory();}});
  ['fillColor','strokeColor'].forEach(id=>$(id).oninput=e=>{const l=getSelectedTextLayer();if(l){ if(id==='fillColor')l.fillColor=e.target.value; else l.strokeColor=e.target.value;drawCanvas();debounceSaveHistory();}});
  $('shadowEnabled').onchange=e=>{const l=getSelectedTextLayer();if(l){l.shadowEnabled=e.target.checked;drawCanvas();saveHistory();}};
  $('addTextBtn').onclick=()=>{const l=addTextLayer($('textInput').value||'新文字',state.outputWidth/2,state.outputHeight*.7);selectLayer(l.id);};
  $('duplicateBtn').onclick=duplicateSelected;
  document.querySelectorAll('.crop-ratio').forEach(b=>b.onclick=()=>{state.cropRatio=b.dataset.ratio;enterCropMode();});
  $('enterCropBtn').onclick=enterCropMode;$('applyCropBtn').onclick=applyCrop;$('cancelCropBtn').onclick=()=>{state.cropMode=false;drawCanvas();};
  $('resetAdjustBtn').onclick=()=>{adjustMeta.forEach(([k,,,,d])=>state.adjustments[k]=d);renderAdjustments();drawCanvas();saveHistory();};
  $('sizePreset').onchange=e=>{if(e.target.value!=='custom'){const [w,h]=e.target.value.split('x').map(Number);$('customWidth').value=w;$('customHeight').value=h;}};
  $('applySizeBtn').onclick=applyOutputSize;
  $('deleteLayerBtn').onclick=deleteSelected;$('toggleVisibleBtn').onclick=()=>toggleLayerProp('visible');$('toggleLockBtn').onclick=()=>toggleLayerProp('locked');
  $('bringForwardBtn').onclick=()=>moveLayer(1);$('sendBackwardBtn').onclick=()=>moveLayer(-1);$('bringTopBtn').onclick=()=>moveLayer(999);
  $('bgFlipXBtn').onclick=()=>{state.backgroundFlipX=!state.backgroundFlipX;drawCanvas();saveHistory();toast('已水平镜像背景');};
  $('bgFlipYBtn').onclick=()=>{state.backgroundFlipY=!state.backgroundFlipY;drawCanvas();saveHistory();toast('已垂直镜像背景');};
  $('mirrorLayerXBtn').onclick=()=>mirrorSelectedLayer('x');$('mirrorLayerYBtn').onclick=()=>mirrorSelectedLayer('y');
  $('jpgQuality').oninput=e=>{state.jpgQuality=Number(e.target.value);$('jpgQualityVal').textContent=e.target.value;};
  $('downloadBtn').onclick=()=>downloadImage(state.exportFormat);$('copyBtn').onclick=copyImage;$('generateBtn').onclick=openPreviewModal;$('generateBtnTop').onclick=openPreviewModal;
  $('undoBtn').onclick=undo;$('redoBtn').onclick=redo;
  canvas.addEventListener('mousedown',startPointer);canvas.addEventListener('mousemove',movePointer);window.addEventListener('mouseup',endPointer);canvas.addEventListener('mouseleave',endPointer);
  canvas.addEventListener('touchstart',startPointer,{passive:false});canvas.addEventListener('touchmove',movePointer,{passive:false});canvas.addEventListener('touchend',endPointer);canvas.addEventListener('touchcancel',endPointer);
  document.addEventListener('keydown',handleKeys);
  $('closeModal').onclick=closeModal;$('modalContinue').onclick=closeModal;$('previewModal').onclick=e=>{if(e.target.id==='previewModal')closeModal();};
  $('modalDownloadPng').onclick=()=>downloadDataUrl(currentFinalDataUrl,'png');$('modalDownloadJpg').onclick=()=>downloadImage('jpg');$('modalCopy').onclick=copyImage;
}
function setupDragUpload(){const dz=$('dropZone');['dragenter','dragover'].forEach(ev=>dz.addEventListener(ev,e=>{e.preventDefault();dz.classList.add('dragover');}));['dragleave','drop'].forEach(ev=>dz.addEventListener(ev,e=>{e.preventDefault();dz.classList.remove('dragover');}));dz.addEventListener('drop',e=>handleUpload(e.dataTransfer.files[0]));}

function loadTemplate(id, push=true){const t=templates.find(x=>x.id===id); if(!t)return; state.backgroundType='template'; state.templateId=id; state.imageDataUrl=''; state.backgroundFlipX=false; state.backgroundFlipY=false; bgImage=new Image(); bgImage.onload=()=>{drawCanvas(); if(push)saveHistory();}; bgImage.src=t.dataUrl; document.querySelectorAll('.template-card').forEach((c,i)=>c.classList.toggle('active',templates[i].id===id));}
function handleUpload(file){if(!file)return; if(!/^image\/(jpeg|png|webp)$/.test(file.type)){toast('请上传 jpg、png 或 webp 图片');return;} const r=new FileReader();r.onload=()=>{const img=new Image();img.onload=()=>{const max=1200, scale=Math.min(1,max/Math.max(img.width,img.height));const c=createCanvas(Math.round(img.width*scale),Math.round(img.height*scale));c.getContext('2d').drawImage(img,0,0,c.width,c.height);state.backgroundType='upload';state.backgroundFlipX=false;state.backgroundFlipY=false;state.imageDataUrl=c.toDataURL('image/png');bgImage=new Image();bgImage.onload=()=>{drawCanvas();saveHistory();};bgImage.src=state.imageDataUrl;};img.src=r.result;};r.readAsDataURL(file);}
function applyOutputSize(){const w=Number($('customWidth').value),h=Number($('customHeight').value); if(w<300||w>3000||h<300||h>3000){toast('请输入 300 到 3000 之间的尺寸');return;} const sx=w/state.outputWidth, sy=h/state.outputHeight; state.layers.forEach(l=>{l.x*=sx;l.y*=sy;l.width*=sx;l.height*=sy;l.fontSize && (l.fontSize*=Math.min(sx,sy));}); state.outputWidth=w; state.outputHeight=h; state.cropRect={x:w*.1,y:h*.1,w:w*.8,h:h*.8}; canvas.width=w;canvas.height=h;drawCanvas();saveHistory();syncUI();}

function addTextLayer(text='新文字',x=400,y=560,push=true){const layer={id:uid(),type:'text',name:'文字',text,x,y,width:360,height:100,scale:1,rotation:0,opacity:1,visible:true,locked:false,zIndex:Date.now(),fontSize:46,fontFamily:'Impact',fontWeight:'900',fillColor:'#ffffff',strokeColor:'#111111',strokeWidth:5,lineHeight:1.2,letterSpacing:0,shadowEnabled:false,bounds:null};state.layers.push(layer);state.selectedLayerId=layer.id;if(push){drawCanvas();saveHistory();renderLayers();syncUI();}return layer;}
function addStickerLayer(sticker){const layer={id:uid(),type:'sticker',name:sticker.label,stickerId:sticker.id,src:sticker.dataUrl,x:state.outputWidth/2,y:state.outputHeight/2,width:180,height:180,scale:1,rotation:0,flipX:false,flipY:false,opacity:1,visible:true,locked:false,zIndex:Date.now(),bounds:null};state.layers.push(layer);state.selectedLayerId=layer.id;drawCanvas();saveHistory();renderLayers();}
function getSelected(){return state.layers.find(l=>l.id===state.selectedLayerId);} function getSelectedTextLayer(){const l=getSelected(); return l&&l.type==='text'?l:null;} function sortedLayers(){return [...state.layers].sort((a,b)=>a.zIndex-b.zIndex);} function uid(){return Math.random().toString(36).slice(2)+Date.now().toString(36);}

function drawCanvas(targetCtx=ctx, outW=state.outputWidth, outH=state.outputHeight, includeSelection=true){
  const c=targetCtx.canvas; if(c.width!==outW)c.width=outW;if(c.height!==outH)c.height=outH; targetCtx.clearRect(0,0,outW,outH); targetCtx.fillStyle='#111217';targetCtx.fillRect(0,0,outW,outH);
  drawBackground(targetCtx,outW,outH); sortedLayers().forEach(l=>drawLayer(targetCtx,l,includeSelection)); if(state.cropMode && includeSelection)drawCropOverlay(targetCtx); updateInfo(); renderLayers(); renderFilters(); updateHistoryButtons();
}
function cssFilter(){const f=filterDefs[state.filter]||filterDefs['原图'],a=state.adjustments;const brightness=f.brightness+a.brightness-100+a.exposure*.7; const contrast=f.contrast+a.contrast-100; const sat=f.saturate+a.saturate-100; const hue=f.hue+a.temperature*.25; const blur=a.blur;return `brightness(${brightness}%) contrast(${contrast}%) saturate(${sat}%) hue-rotate(${hue}deg) sepia(${f.sepia}%) grayscale(${f.grayscale}%) blur(${blur}px)`;}
function drawBackground(x,w,h){
  if(!bgImage){x.fillStyle='#222';x.fillRect(0,0,w,h);return;}
  x.save();x.filter=cssFilter();
  const iw=bgImage.width,ih=bgImage.height; let dx=0,dy=0,dw=w,dh=h;
  if(state.fitMode==='contain'){const sc=Math.min(w/iw,h/ih);dw=iw*sc;dh=ih*sc;dx=(w-dw)/2;dy=(h-dh)/2;}
  else if(state.fitMode==='cover'){const sc=Math.max(w/iw,h/ih);dw=iw*sc;dh=ih*sc;dx=(w-dw)/2;dy=(h-dh)/2;}
  else if(state.fitMode==='center'){dw=Math.min(iw,w);dh=Math.min(ih,h);dx=(w-dw)/2;dy=(h-dh)/2;}
  if(state.backgroundFlipX||state.backgroundFlipY){
    x.translate(state.backgroundFlipX?w:0,state.backgroundFlipY?h:0);
    x.scale(state.backgroundFlipX?-1:1,state.backgroundFlipY?-1:1);
  }
  x.drawImage(bgImage,dx,dy,dw,dh); x.restore();
  if(state.adjustments.vignette>0)drawVignette(x,w,h,state.adjustments.vignette);
}
function drawVignette(x,w,h,v){const g=x.createRadialGradient(w/2,h/2,Math.min(w,h)*.2,w/2,h/2,Math.max(w,h)*.7);g.addColorStop(0,'rgba(0,0,0,0)');g.addColorStop(1,`rgba(0,0,0,${v/100})`);x.fillStyle=g;x.fillRect(0,0,w,h);}
function drawLayer(x,l,includeSelection=true){if(!l.visible)return; x.save();x.globalAlpha=l.opacity;x.translate(l.x,l.y);x.rotate(l.rotation);x.scale((l.flipX?-1:1)*l.scale,(l.flipY?-1:1)*l.scale); if(l.type==='text')drawTextLayer(x,l); else drawStickerLayer(x,l); x.restore(); updateBounds(l); if(includeSelection&&state.selectedLayerId===l.id)drawSelection(x,l);}
function drawTextLayer(x,l){const maxW=Math.min(state.outputWidth*.85, Math.max(80,l.width));x.font=`${l.fontWeight} ${l.fontSize}px ${l.fontFamily}`;x.textAlign='center';x.textBaseline='middle';x.lineJoin='round';const lines=wrapText(x,l.text,maxW);const lh=l.fontSize*l.lineHeight;const total=(lines.length-1)*lh; if(l.shadowEnabled){x.shadowColor='rgba(0,0,0,.55)';x.shadowBlur=10;x.shadowOffsetX=4;x.shadowOffsetY=4;} lines.forEach((line,i)=>{const y=i*lh-total/2;x.lineWidth=l.strokeWidth;x.strokeStyle=l.strokeColor;x.fillStyle=l.fillColor;drawTextWithLetterSpacing(x,line,0,y,l.letterSpacing,'stroke');drawTextWithLetterSpacing(x,line,0,y,l.letterSpacing,'fill');}); l.height=Math.max(l.fontSize, lines.length*lh); l.width=maxW;}
function drawStickerLayer(x,l){
  const img = getStickerImage(l);
  if(img && img.complete){
    x.drawImage(img,-l.width/2,-l.height/2,l.width,l.height);
  }else{
    x.fillStyle='rgba(255,255,255,.12)';x.fillRect(-l.width/2,-l.height/2,l.width,l.height);
    x.fillStyle='#fff';x.textAlign='center';x.textBaseline='middle';x.font='32px Microsoft YaHei';x.fillText(l.name||'贴纸',0,0);
  }
}
function getStickerImage(l){
  const built=stickers.find(s=>s.id===l.stickerId); if(built)return built.img;
  if(l.src){ if(!layerImageCache.has(l.id)){const img=new Image();img.onload=()=>drawCanvas();img.src=l.src;layerImageCache.set(l.id,img);} return layerImageCache.get(l.id); }
  return null;
}
function wrapText(x,text,maxWidth){if(!text)return[]; const units=text.match(/[a-zA-Z0-9]+|\s+|[^a-zA-Z0-9\s]/g)||[]; const lines=[]; let line=''; for(const u of units){const test=line+u; if(x.measureText(test).width>maxWidth && line){lines.push(line.trim()); line=u.trimStart();} else line=test;} if(line.trim())lines.push(line.trim()); return lines.length?lines:[''];}
function drawTextWithLetterSpacing(x,text,px,py,sp,mode){if(!sp){mode==='fill'?x.fillText(text,px,py):x.strokeText(text,px,py);return;} const widths=[...text].map(ch=>x.measureText(ch).width), total=widths.reduce((a,b)=>a+b,0)+sp*(widths.length-1); let start=px-total/2; [...text].forEach((ch,i)=>{const cx=start+widths[i]/2; mode==='fill'?x.fillText(ch,cx,py):x.strokeText(ch,cx,py); start+=widths[i]+sp;});}
function updateBounds(l){l.bounds={x:l.x,y:l.y,w:l.width*l.scale,h:l.height*l.scale,rotation:l.rotation};}
function drawSelection(x,l){x.save();x.translate(l.x,l.y);x.rotate(l.rotation);x.strokeStyle='#22c55e';x.lineWidth=3;x.setLineDash([8,6]);x.strokeRect(-l.width*l.scale/2,-l.height*l.scale/2,l.width*l.scale,l.height*l.scale);x.setLineDash([]);drawHandle(x,l.width*l.scale/2,l.height*l.scale/2,'#22c55e');drawHandle(x,0,-l.height*l.scale/2-34,'#06b6d4');x.restore();}
function drawHandle(x,px,py,color){x.fillStyle=color;x.beginPath();x.arc(px,py,10,0,Math.PI*2);x.fill();}
function drawCropOverlay(x){
  const r=state.cropRect,w=x.canvas.width,h=x.canvas.height;
  x.save();x.fillStyle='rgba(0,0,0,.52)';
  x.fillRect(0,0,w,r.y);x.fillRect(0,r.y+r.h,w,h-r.y-r.h);x.fillRect(0,r.y,r.x,r.h);x.fillRect(r.x+r.w,r.y,w-r.x-r.w,r.h);
  x.strokeStyle='#22c55e';x.lineWidth=4;x.strokeRect(r.x,r.y,r.w,r.h);
  x.fillStyle='#22c55e';[[r.x,r.y],[r.x+r.w,r.y],[r.x,r.y+r.h],[r.x+r.w,r.y+r.h]].forEach(([cx,cy])=>{x.beginPath();x.arc(cx,cy,8,0,Math.PI*2);x.fill();});
  x.restore();
}

function getPoint(e){if(e.touches&&e.touches[0])e=e.touches[0];const rect=canvas.getBoundingClientRect();return{x:(e.clientX-rect.left)*canvas.width/rect.width,y:(e.clientY-rect.top)*canvas.height/rect.height};}
function startPointer(e){e.preventDefault();const p=getPoint(e); if(state.cropMode){interaction={mode:'crop',start:p,original:{...state.cropRect}};return;} const hit=hitTest(p); if(hit){selectLayer(hit.id); const ctl=hitControl(p,hit); interaction={mode:ctl||'move',layerId:hit.id,start:p,original:{...hit}}; canvas.style.cursor='grabbing';} else {state.selectedLayerId=null; interaction={mode:null}; syncUI(); drawCanvas();}}
function movePointer(e){const p=getPoint(e); if(!interaction.mode){const h=hitTest(p);canvas.style.cursor=h?'move':'default';return;} e.preventDefault(); if(interaction.mode==='crop'){const dx=p.x-interaction.start.x,dy=p.y-interaction.start.y;state.cropRect={...interaction.original,x:clamp(interaction.original.x+dx,0,canvas.width-50),y:clamp(interaction.original.y+dy,0,canvas.height-50)};drawCanvas();return;} const l=getSelected(); if(!l||l.locked)return; const dx=p.x-interaction.start.x,dy=p.y-interaction.start.y; if(interaction.mode==='move'){l.x=clamp(interaction.original.x+dx,0,state.outputWidth);l.y=clamp(interaction.original.y+dy,0,state.outputHeight);} if(interaction.mode==='scale'){const dist0=Math.hypot(interaction.start.x-interaction.original.x,interaction.start.y-interaction.original.y);const dist1=Math.hypot(p.x-interaction.original.x,p.y-interaction.original.y);l.scale=clamp((interaction.original.scale||1)*(dist1/Math.max(20,dist0)),.15,6);} if(interaction.mode==='rotate'){l.rotation=Math.atan2(p.y-l.y,p.x-l.x)+Math.PI/2;} drawCanvas();}
function endPointer(){if(interaction.mode){saveHistory();} interaction={mode:null};canvas.style.cursor='default';}
function hitTest(p){const layers=sortedLayers().reverse();return layers.find(l=>l.visible&&!l.locked&&pointInRotatedRect(p,l));}
function pointInRotatedRect(p,l){const dx=p.x-l.x,dy=p.y-l.y;const cos=Math.cos(-l.rotation),sin=Math.sin(-l.rotation);const rx=(dx*cos-dy*sin)/l.scale, ry=(dx*sin+dy*cos)/l.scale;return Math.abs(rx)<=l.width/2&&Math.abs(ry)<=l.height/2;}
function hitControl(p,l){const sx=l.x+Math.cos(l.rotation)*l.width*l.scale/2-Math.sin(l.rotation)*l.height*l.scale/2, sy=l.y+Math.sin(l.rotation)*l.width*l.scale/2+Math.cos(l.rotation)*l.height*l.scale/2; if(Math.hypot(p.x-sx,p.y-sy)<24)return 'scale'; const rx=l.x+Math.sin(l.rotation)*(l.height*l.scale/2+34), ry=l.y-Math.cos(l.rotation)*(l.height*l.scale/2+34); if(Math.hypot(p.x-rx,p.y-ry)<24)return 'rotate'; return null;}
function selectLayer(id){state.selectedLayerId=id;syncUI();drawCanvas();}
function handleKeys(e){if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='z'){e.preventDefault();e.shiftKey?redo():undo();} else if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='y'){e.preventDefault();redo();} else if(e.key==='Delete'){deleteSelected();} else if(e.key==='Escape'){state.selectedLayerId=null;drawCanvas();}}

function enterCropMode(){state.cropMode=true;const r=ratioToNum(state.cropRatio),w=state.outputWidth*.72,h=r?w/r:state.outputHeight*.72;if(r)state.cropRect={x:(state.outputWidth-w)/2,y:(state.outputHeight-h)/2,w,h};drawCanvas();}
function ratioToNum(v){if(v==='free')return null;const [a,b]=v.split(':').map(Number);return a/b;}
function applyCrop(){
  const r={...state.cropRect}; if(!state.cropMode)return;
  const clean=createCanvas(state.outputWidth,state.outputHeight);
  const oldCrop=state.cropMode; state.cropMode=false;
  drawCanvas(clean.getContext('2d'),state.outputWidth,state.outputHeight,false);
  state.cropMode=oldCrop;
  const out=createCanvas(Math.round(r.w),Math.round(r.h));
  out.getContext('2d').drawImage(clean,r.x,r.y,r.w,r.h,0,0,out.width,out.height);
  state.outputWidth=out.width;state.outputHeight=out.height;
  state.imageDataUrl=out.toDataURL('image/png');state.backgroundType='upload';state.backgroundFlipX=false;state.backgroundFlipY=false;
  bgImage=new Image();bgImage.onload=()=>{state.layers.forEach(l=>{l.x=clamp(l.x-r.x,0,state.outputWidth);l.y=clamp(l.y-r.y,0,state.outputHeight);});state.cropMode=false;state.cropRect={x:state.outputWidth*.1,y:state.outputHeight*.1,w:state.outputWidth*.8,h:state.outputHeight*.8};syncUI();drawCanvas();saveHistory();toast('裁剪已应用');};bgImage.src=state.imageDataUrl;
}

function applyFilter(){} function applyAdjustments(){}
function generateFinalImage(format='png'){const out=createCanvas(state.outputWidth,state.outputHeight);drawCanvas(out.getContext('2d'),state.outputWidth,state.outputHeight,false);return out.toDataURL(format==='jpg'?'image/jpeg':'image/png',state.jpgQuality);}
function openPreviewModal(){currentFinalDataUrl=generateFinalImage('png');$('finalPreview').src=currentFinalDataUrl;const kb=Math.round(currentFinalDataUrl.length*0.75/1024);$('finalInfo').textContent=`尺寸：${state.outputWidth} × ${state.outputHeight} px｜估算大小：${kb} KB`;$('previewModal').classList.remove('hidden');saveWorkToGallery(currentFinalDataUrl);}
function closeModal(){$('previewModal').classList.add('hidden');}
function downloadImage(format='png'){const url=generateFinalImage(format);downloadDataUrl(url,format);saveWorkToGallery(url);}
function downloadDataUrl(url,format){const a=document.createElement('a');a.href=url;a.download=`${state.filePrefix||'meme-workshop'}-${Date.now()}.${format}`;a.click();toast('已生成下载文件');}
async function copyImage(){try{const url=generateFinalImage('png');const blob=await (await fetch(url)).blob();await navigator.clipboard.write([new ClipboardItem({'image/png':blob})]);toast('图片已复制到剪贴板');}catch{toast('当前浏览器不支持复制图片，请使用下载功能');}}
function saveWorkToGallery(dataUrl){try{let list=JSON.parse(localStorage.getItem('memeGallery')||'[]');list.unshift({id:uid(),time:new Date().toLocaleString(),dataUrl,state:getCurrentState()});list=list.slice(0,12);localStorage.setItem('memeGallery',JSON.stringify(list));renderGallery();}catch{toast('浏览器存储空间不足，请先删除部分历史作品');}}
function renderGallery(){const box=$('galleryGrid');if(!box)return;const list=JSON.parse(localStorage.getItem('memeGallery')||'[]');box.innerHTML=list.length?'':'<p class="mini-hint">暂无生成作品。</p>';list.forEach(item=>{const d=document.createElement('div');d.className='gallery-card';d.innerHTML=`<img src="${item.dataUrl}"><span>${item.time}</span><button class="btn secondary full">重新编辑</button><button class="btn ghost full">下载</button><button class="btn danger full">删除</button>`;const [edit,down,del]=d.querySelectorAll('button');edit.onclick=()=>applyState(item.state,true);down.onclick=()=>downloadDataUrl(item.dataUrl,'png');del.onclick=()=>{const n=list.filter(x=>x.id!==item.id);localStorage.setItem('memeGallery',JSON.stringify(n));renderGallery();};box.appendChild(d);});}

function getCurrentState(){return JSON.parse(JSON.stringify(state));}
function saveHistory(initial=false){clearTimeout(saveTimer);const snap=getCurrentState(); if(!initial)redoStack=[];undoStack.push(snap);if(undoStack.length>50)undoStack.shift();updateHistoryButtons();}
function debounceSaveHistory(){clearTimeout(saveTimer);saveTimer=setTimeout(()=>saveHistory(),500);}
function undo(){if(undoStack.length<=1)return;redoStack.push(undoStack.pop());applyState(undoStack[undoStack.length-1],false);}
function redo(){if(!redoStack.length)return;const s=redoStack.pop();undoStack.push(s);applyState(s,false);}
function applyState(s,push=false){state=JSON.parse(JSON.stringify(s)); if(state.backgroundType==='template'){loadTemplate(state.templateId,false);} else if(state.imageDataUrl){bgImage=new Image();bgImage.onload=()=>{syncUI();drawCanvas();};bgImage.src=state.imageDataUrl;} syncUI();drawCanvas();if(push)saveHistory();}
function updateHistoryButtons(){$('undoBtn').disabled=undoStack.length<=1;$('redoBtn').disabled=!redoStack.length;}

function syncUI(){canvas.width=state.outputWidth;canvas.height=state.outputHeight;$('canvasInfo').textContent=`${state.outputWidth} × ${state.outputHeight} px`;$('customWidth').value=state.outputWidth;$('customHeight').value=state.outputHeight;$('fitMode').value=state.fitMode;$('exportFormat').value=state.exportFormat;$('filePrefix').value=state.filePrefix;$('jpgQuality').value=state.jpgQuality;$('jpgQualityVal').textContent=state.jpgQuality;const l=getSelectedTextLayer(); if(l){$('textInput').value=l.text;$('fontFamily').value=l.fontFamily;$('fontWeight').value=l.fontWeight;$('fontSize').value=Math.round(l.fontSize);$('fontSizeVal').textContent=Math.round(l.fontSize);$('strokeWidth').value=l.strokeWidth;$('strokeWidthVal').textContent=l.strokeWidth;$('lineHeight').value=l.lineHeight;$('lineHeightVal').textContent=l.lineHeight;$('letterSpacing').value=l.letterSpacing;$('letterSpacingVal').textContent=l.letterSpacing;$('fillColor').value=l.fillColor;$('strokeColor').value=l.strokeColor;$('shadowEnabled').checked=l.shadowEnabled;} renderLayers();}
function renderLayers(){const box=$('layerList');if(!box)return;box.innerHTML='';sortedLayers().reverse().forEach(l=>{const d=document.createElement('button');d.className='layer-item'+(l.id===state.selectedLayerId?' active':'');d.innerHTML=`<span>${l.type==='text'?'T':'贴'} ${l.name||l.text||'图层'}</span><span>${l.visible?'👁':'🙈'} ${l.locked?'🔒':''}</span>`;d.onclick=()=>selectLayer(l.id);box.appendChild(d);});}
function updateInfo(){$('canvasInfo').textContent=`${state.outputWidth} × ${state.outputHeight} px`;}

function deleteSelected(){if(!state.selectedLayerId)return;state.layers=state.layers.filter(l=>l.id!==state.selectedLayerId);state.selectedLayerId=null;drawCanvas();saveHistory();}
function duplicateSelected(){const l=getSelected();if(!l)return;const n=JSON.parse(JSON.stringify(l));n.id=uid();n.x+=30;n.y+=30;n.zIndex=Date.now();state.layers.push(n);state.selectedLayerId=n.id;drawCanvas();saveHistory();}
function toggleLayerProp(prop){const l=getSelected();if(!l)return;l[prop]=!l[prop];drawCanvas();saveHistory();}
function moveLayer(delta){const l=getSelected();if(!l)return;if(delta===999)l.zIndex=Date.now()+9999;else l.zIndex+=delta*1000;drawCanvas();saveHistory();}
function mirrorSelectedLayer(axis){
  const l=getSelected(); if(!l){toast('请先在画布或图层列表中选择一个文字/贴纸图层');return;}
  if(axis==='x') l.flipX=!l.flipX; else l.flipY=!l.flipY;
  drawCanvas();saveHistory();toast(axis==='x'?'已水平镜像图层':'已垂直镜像图层');
}
function clamp(n,min,max){return Math.max(min,Math.min(max,n));}
function toast(msg){const t=$('toast');t.textContent=msg;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2200);}

window.addEventListener('load',initApp);
