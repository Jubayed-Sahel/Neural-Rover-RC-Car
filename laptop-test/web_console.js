'use strict';
const $=id=>document.getElementById(id), directions=[...document.querySelectorAll('[data-direction]')];
let snapshot=null,sequence=0,gesture=0,held=null,lease=null,renewTimer=null,videoRequested=false,videoError=false,initialized=false,reviewId=null,seenTask=null,toastTimer;
const pages={overview:['Mission control','Your live view, recognition and rover controls.'],people:['People library','Enroll participants and manage recognition profiles.'],devices:['Devices & network','Connect your camera, rover and phone.'],alerts:['Telegram alerts','Manage private recognition notifications.'],demo:['Demo readiness','Prepare your portable university demonstration.']};
function text(id,value){$(id).textContent=value??'';}
function status(id,label,state){
  text(id,label);
  $(id).dataset.state=state;
}
function renderRover(rover,control){
  const connecting=rover.status==='Connecting';
  const state=rover.connected?'ready':connecting?'pending':'offline';
  status('roverBadge',rover.connected?'Connected':connecting?'Connecting…':'Disconnected',state);
  text('roverAddress',rover.address||'No ESP32 address saved');
  $('roverConnection').dataset.state=state;
  text('controlStatus',rover.connected
    ? control.control_active?'Driving from '+control.control_owner:'Ready to drive'
    : rover.status==='Disconnected'
      ? rover.address?'Click Connect to enable driving.':'Enter the main ESP32 address to enable driving.'
      : rover.status);
  text('deviceRoverStatus',rover.status);
  $('quickConnect').disabled=connecting;
  text('quickConnect',connecting?'Connecting…':rover.connected?'Reconnect':'Connect');
  if(!control.can_drive&&held)stop();
  directions.forEach(button=>button.disabled=!control.can_drive);
}
async function connectRover(address){
  const value=address.trim();
  if(!value){toast('Enter the main ESP32 IP address.',true);return;}
  $('quickConnect').disabled=true;
  text('quickConnect','Connecting…');
  try{
    await request('/api/console/rover/connect',{address:value});
    $('quickAddress').value=value;
    $('roverForm').elements.address.value=value;
    toast('Checking the connection to '+value+'…');
  }catch(error){
    $('quickConnect').disabled=false;
    text('quickConnect','Connect');
    toast(error.message,true);
  }
}
function toast(message,error=false){text('notice',message);$('notice').hidden=false;$('notice').className=error?'error':'';clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('notice').hidden=true,7000);}
async function request(path,body,keepalive=false){const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),body?12000:3500);try{const response=await fetch(path,{method:body?'POST':'GET',headers:body?{'Content-Type':'application/json'}:{},body:body?JSON.stringify(body):undefined,credentials:'same-origin',cache:'no-store',signal:controller.signal,keepalive});const result=await response.json();if(!response.ok)throw new Error(result.error||'Request failed.');return result;}finally{clearTimeout(timeout);}}
async function action(name,body={}){try{const result=await request('/api/console/'+name,body);if(!result.task_id)toast('Saved.');return result;}catch(error){toast(error.message,true);if($('personDialog').open)text('personError',error.message);throw error;}}
function click(id,fn){$(id).addEventListener('click',()=>Promise.resolve().then(fn).catch(()=>{}));}
function ask(message){return new Promise(resolve=>{const dialog=$('confirmDialog');text('confirmMessage',message);let answer=false;const finish=()=>{dialog.removeEventListener('close',finish);resolve(answer);};$('confirmYes').onclick=()=>{answer=true;dialog.close();};$('confirmNo').onclick=()=>dialog.close();dialog.addEventListener('close',finish);dialog.showModal();});}
function navigate(page){if(!pages[page])page='overview';stop();document.querySelectorAll('.page').forEach(el=>el.hidden=el.id!==page);document.querySelectorAll('[data-page]').forEach(el=>el.classList.toggle('selected',el.dataset.page===page));text('pageTitle',pages[page][0]);text('subtitle',pages[page][1]);text('breadcrumb',page==='overview'?'OPERATIONS':pages[page][0].toUpperCase());}
document.querySelectorAll('[data-page]').forEach(el=>el.addEventListener('click',()=>{location.hash=el.dataset.page;}));window.addEventListener('hashchange',()=>navigate(location.hash.slice(1)));navigate(location.hash.slice(1));
function clearHeld(){gesture++;held=null;lease=null;clearTimeout(renewTimer);directions.forEach(el=>el.classList.remove('held'));}
function stop(force=false){const active=held!==null||lease!==null;clearHeld();if(snapshot&&(force||active))request('/api/control',{operation:'stop',sequence:++sequence},true).catch(()=>{});}
async function start(event,button){event.preventDefault();if(!snapshot?.control.can_drive||held)return;const current=++gesture,direction=button.dataset.direction;held=button;button.classList.add('held');button.setPointerCapture(event.pointerId);try{const begun=await request('/api/control',{operation:'begin',direction,epoch:snapshot.control.epoch,sequence:++sequence});if(current!==gesture||held!==button)return;lease=begun.lease;async function renew(){if(current!==gesture||held!==button)return;try{await request('/api/control',{operation:'hold',direction,lease,epoch:begun.epoch,sequence:++sequence});if(current===gesture&&held===button)renewTimer=setTimeout(renew,120);}catch(error){stop();toast(error.message,true);}}renewTimer=setTimeout(renew,120);}catch(error){if(current===gesture){stop();toast(error.message,true);}}}
directions.forEach(button=>{button.addEventListener('pointerdown',event=>start(event,button));button.addEventListener('pointermove',event=>{if(held!==button)return;const r=button.getBoundingClientRect();if(event.clientX<r.left||event.clientX>r.right||event.clientY<r.top||event.clientY>r.bottom)stop();});button.addEventListener('lostpointercapture',()=>stop());button.addEventListener('contextmenu',event=>event.preventDefault());});
['pointerup','pointercancel','blur','pagehide'].forEach(name=>window.addEventListener(name,()=>stop()));document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});document.addEventListener('keydown',event=>{if(event.key==='Escape')stop(true);});click('globalStop',()=>stop(true));click('padStop',()=>stop(true));
$('camera').addEventListener('load',()=>{videoError=false;});$('camera').addEventListener('error',()=>{videoRequested=false;videoError=true;$('camera').hidden=true;$('videoNote').hidden=false;});
function element(tag,content,className){const el=document.createElement(tag);if(content!==undefined)el.textContent=content;if(className)el.className=className;return el;}
let peopleSignature='';function renderPeople(people){const signature=JSON.stringify(people);if(signature===peopleSignature)return;peopleSignature=signature;const target=$('peopleList');target.replaceChildren();if(!people.length){target.append(element('div','No profiles yet. Add a person to begin recognition.','empty'));return;}people.forEach(person=>{const card=element('article',undefined,'person-card');card.append(element('div',person.name.slice(0,2).toUpperCase(),'person-avatar'),element('h3',person.name),element('p',[person.role,person.id].filter(Boolean).join(' · ')||'No role or ID'),element('p',`${person.templates} face templates · Alerts ${person.notify?'on':'off'}`));const buttons=element('div',undefined,'inline');const edit=element('button','Manage profile');edit.onclick=()=>openPerson(person);const remove=element('button','Remove','danger');remove.onclick=async()=>{if(await ask(`Remove ${person.name} and their saved face templates?`))action('people/delete',{name:person.name,confirmed:true}).catch(()=>{});};buttons.append(edit,remove);card.append(buttons);target.append(card);});}
function renderEvents(events){const target=$('events');target.replaceChildren();events.slice(0,7).forEach(item=>{const row=element('div',undefined,'event');row.append(element('time',item.time),element('strong',item.title),element('span',item.detail));target.append(row);});}
function renderChecks(checks){const target=$('readinessResults');target.className='';target.replaceChildren();checks.forEach(check=>{const row=element('div',undefined,'check-result');row.append(element('span',check.level,'pill '+check.level),element('strong',check.title),element('p',check.detail));target.append(row);});}
function renderTask(task){$('job').hidden=!task||task.status!=='running';if(!task)return;text('jobKind',task.kind);text('jobMessage',task.message);$('cancelJob').hidden=task.kind!=='live enrollment';if(task.status==='running'||seenTask===task.id)return;seenTask=task.id;if(task.status==='error'){toast(task.message,true);text('personError',task.message);return;}if(task.kind==='photo review'||task.kind==='live enrollment'){reviewId=task.result.id;text('reviewResult',task.result.summary);text('personError','');}if(task.kind==='photo test'){$('photoResult').hidden=false;$('photoResult').replaceChildren(element('h2','Photo test result'),element('p',`${task.result.label} · similarity ${task.result.similarity}`),element('p',task.result.note));}if(task.kind==='readiness check')renderChecks(task.result.checks);toast(task.kind+' completed.');}
function render(next){snapshot=next;sequence=Math.max(sequence,next.control.sequence);status('cameraBadge',next.control.video_live?'Live':next.camera.running?'Waiting for video':'Stopped',next.control.video_live?'ready':next.camera.running?'pending':'offline');text('cameraDetail',next.camera.preview?'Preview only':next.camera.mode+' recognition');renderRover(next.rover,next.control);text('peopleCount',next.people.length+' profile'+(next.people.length===1?'':'s'));status('alertBadge',next.telegram.enabled?'Alerts on':next.telegram.configured?'Paired':'Not paired',next.telegram.configured?'ready':'offline');text('cameraStatus',next.camera.status);text('matches',next.control.matches);text('liveBadge',next.control.video_live?'LIVE':'OFFLINE');$('liveBadge').className='pill'+(next.control.video_live?' live':'');const m=next.camera.metrics;text('metrics',m.source_width?`${m.source_width} × ${m.source_height} · ${Math.round(m.analysis_ms||0)} ms analysis`:'');$('camera').hidden=!next.control.video_live||videoError;$('videoNote').hidden=next.control.video_live&&!videoError;if(next.control.video_live&&!videoRequested){videoRequested=true;$('camera').src='/video?t='+Date.now();}text('telegramStatus',next.telegram.configured?'Private chat paired':'Not paired');text('telegramEnabled',next.telegram.enabled?'Notifications enabled':'Notifications paused');text('toggleAlerts',next.telegram.enabled?'Pause alerts':'Enable alerts');$('telegramPair').hidden=!next.telegram.pairing;if(next.telegram.pairing){text('botName','@'+next.telegram.pairing.username);text('botCode',next.telegram.pairing.code);}text('phoneUrl',next.phone.url||'No network address found');$('phoneUrl').href=next.phone.url||'#';text('phoneCode',next.phone.code);if(!initialized){const form=$('cameraForm');['host','username','stream'].forEach(key=>form.elements[key].value=next.camera[key]||'');$('quickAddress').value=next.rover.address;$('roverForm').elements.address.value=next.rover.address;$('operation').value=next.camera.preview?'preview':'recognition';$('matching').value=next.camera.mode;initialized=true;}renderPeople(next.people);renderEvents(next.events);renderTask(next.task);}
async function poll(){try{render(await request('/api/console/state'));}catch(error){directions.forEach(button=>button.disabled=true);stop();text('controlStatus','Workspace connection lost. Movement stopped.');text('cameraBadge','Unavailable');status('roverBadge','Unavailable','offline');$('roverConnection').dataset.state='offline';$('quickConnect').disabled=true;text('deviceRoverStatus','Workspace connection lost.');}finally{setTimeout(poll,650);}}
click('startCamera',()=>action('camera/start',{mode:$('matching').value,preview:$('operation').value==='preview'}));click('stopCamera',()=>action('camera/stop'));click('disconnectRover',()=>action('rover/disconnect'));click('toggleAlerts',()=>action('telegram/enable',{enabled:!snapshot?.telegram.enabled}));click('testTelegram',()=>action('telegram/test'));click('completeTelegram',()=>action('telegram/complete'));click('checkReadiness',()=>action('readiness'));click('cancelJob',()=>action('task/cancel'));click('shutdown',async()=>{if(await ask('Stop the rover and shut down this workspace?')){stop(true);await action('session/shutdown');toast('Workspace shut down. Double-click the launcher to reopen.');}});
['pairPhone','devicePair'].forEach(id=>click(id,()=>$('phoneDialog').showModal()));document.querySelectorAll('[data-close]').forEach(button=>button.addEventListener('click',()=>button.closest('dialog').close()));
click('copyPhone',async()=>{
  const url=snapshot?.phone.url;
  if(!url){text('copyPhone','No phone address available');return;}
  try{
    await navigator.clipboard.writeText(url);
    text('copyPhone','Address copied');
  }catch{
    const range=document.createRange();
    range.selectNodeContents($('phoneUrl'));
    const selection=window.getSelection();
    selection.removeAllRanges();
    selection.addRange(range);
    text('copyPhone','Press Ctrl+C to copy');
  }
});
$('phoneDialog').addEventListener('close',()=>text('copyPhone','Copy phone address'));
function formAction(id,name,transform=value=>value){$(id).addEventListener('submit',async event=>{event.preventDefault();try{await action(name,transform(Object.fromEntries(new FormData(event.target))));if(id==='cameraForm')event.target.elements.password.value='';if(id==='telegramForm')event.target.elements.token.value='';}catch{}});}
formAction('cameraForm','camera/save');formAction('telegramForm','telegram/begin');
for(const id of ['quickRoverForm','roverForm']) $(id).addEventListener('submit',event=>{event.preventDefault();connectRover(event.currentTarget.elements.address.value);});
function openPerson(person=null){reviewId=null;$('personForm').reset();const form=$('personForm');form.elements.name.readOnly=!!person;if(person){['name','id','role'].forEach(key=>form.elements[key].value=person[key]||'');form.elements.notify.checked=person.notify;}text('personTitle',person?'Manage '+person.name:'Add person');text('reviewResult',person?'Save details directly, or add new face views below.':'Check photos or collect live views before saving a new person.');text('personError','');$('enrollPhotos').value='';$('personDialog').showModal();}
click('addPerson',()=>openPerson());click('capturePerson',()=>action('people/capture',{name:$('personForm').elements.name.value}));
$('personForm').addEventListener('submit',async event=>{event.preventDefault();const form=event.target,body=Object.fromEntries(new FormData(form));body.notify=form.elements.notify.checked;if(reviewId){body.review_id=reviewId;if(body.mode==='replace'&&snapshot.people.some(person=>person.name===body.name)){if(!await ask('Replace all saved face templates for '+body.name+'?'))return;body.confirm_replace=true;}}try{await action('people/save',body);$('personDialog').close();}catch{}});
async function upload(files){if(!files.length||files.length>10)throw new Error('Choose 1–10 photos.');const result=[];for(const file of files){if(file.size>20000000)throw new Error('Each photo must be under 20 MB.');const bitmap=await createImageBitmap(file);try{if(bitmap.width*bitmap.height>24000000)throw new Error('Each photo must be under 24 megapixels.');const ratio=Math.min(1,1280/Math.max(bitmap.width,bitmap.height)),canvas=document.createElement('canvas');canvas.width=Math.round(bitmap.width*ratio);canvas.height=Math.round(bitmap.height*ratio);canvas.getContext('2d').drawImage(bitmap,0,0,canvas.width,canvas.height);result.push({name:file.name,data:canvas.toDataURL('image/jpeg',.92)});}finally{bitmap.close();}}return result;}
$('enrollPhotos').addEventListener('change',async event=>{try{reviewId=null;text('reviewResult','Checking selected photos…');await action('photos/review',{photos:await upload([...event.target.files])});}catch(error){text('reviewResult',error.message);toast(error.message,true);}event.target.value='';});$('testPhoto').addEventListener('change',async event=>{try{await action('photos/test',{photos:await upload([...event.target.files])});}catch(error){toast(error.message,true);}event.target.value='';});
poll();
