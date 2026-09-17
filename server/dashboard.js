const $=id=>document.getElementById(id);
let state, activity, pictures=[], editingKind, editingProgram, busy=false, scheduleDirty=false;
const defaults={hourly:'06:00',today:'09:30',daily:'17:00',tomorrow:'21:00'};
const localPrograms=new Set(['clock-calendar','photo-frame','countdown','daylight']);
const iconPaths={photo:'<rect x="3" y="3" width="18" height="18" rx="3"/><circle cx="8" cy="8" r="1.5"/><path d="m3 17 6-6 4 4 3-3 5 5"/>',clock:'<circle cx="12" cy="12" r="9"/><path d="M12 6v6l4 2"/>',sun:'<circle cx="12" cy="12" r="4"/><path d="M12 1v3m0 16v3M1 12h3m16 0h3M4 4l2 2m12 12 2 2M4 20l2-2M18 6l2-2"/>',calendar:'<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M7 2v6m10-6v6M3 11h18m-14 4h3m4 0h3"/>',trash:'<path d="M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7m4-7v7"/>',edit:'<path d="m4 15 11-11 5 5L9 20H4zM13 6l5 5"/>',chevron:'<path d="m9 5 7 7-7 7"/>',close:'<path d="m6 6 12 12M6 18 18 6"/>',plus:'<path d="M12 4v16M4 12h16"/>'};
function svgIcon(kind){const span=element('span');span.innerHTML='<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'+iconPaths[kind]+'</svg>';return span.firstChild}
function iconButton(kind,label,action){const node=button('',action);node.append(svgIcon(kind));node.className='icon-button';node.title=label;node.setAttribute('aria-label',label);return node}
const icons={'clock-calendar':'clock','photo-frame':'photo',countdown:'calendar',daylight:'sun','simple-weather':'sun','weather-cal':'sun'};
async function api(path, data, method='POST'){
  const response=await fetch(path,data===undefined?{}:{method,headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const result=await response.json();if(!response.ok)throw Error(result.error||'Request failed');return result;
}
function nameFor(id){return state.programs.find(p=>p.id===id)?.name||'Reminder'}
function settingsData(){const keys=['program_schedule_enabled','program_schedule','refresh_mode','adaptive_refresh','active_program','server_refresh_seconds','device_refresh_seconds','enabled_pages','page_schedule','advisories','app_settings'];return Object.fromEntries(keys.map(key=>[key,structuredClone(state[key])]))}
function timeAt(epoch,date=true){return new Intl.DateTimeFormat(undefined,{timeZone:state.timezone,...(date?{month:'short',day:'numeric'}:{}),hour:'numeric',minute:'2-digit',second:'2-digit'}).format(new Date(epoch*1000))}
function element(tag,text,className){const node=document.createElement(tag);if(text!==undefined)node.textContent=text;if(className)node.className=className;return node}
function button(text,action){const node=element('button',text);node.type='button';node.onclick=action;return node}
function render(){
  const chosen=state.current_program;
  $('programSummary').textContent='Scheduled now: '+nameFor(chosen);
  $('serverInterval').textContent=localPrograms.has(chosen)?'Program timing is configured in its settings.':`Server generates weather images every ${state.server_refresh_seconds/60} minutes.`;
  $('interval').textContent=state.refresh_mode==='adaptive'&&chosen==='simple-weather'?`Adaptive ${state.adaptive_refresh.min_seconds/60}–${state.adaptive_refresh.max_seconds/60} min`:localPrograms.has(chosen)?'Program timing':`${state.device_refresh_seconds/60} min`;
  $('wakePreview').textContent=localPrograms.has(chosen)||chosen==='reminder'?'The next fetch follows the program, reminder, and schedule boundaries.':state.refresh_preview?`On next fetch: sleep ${Math.round(state.refresh_preview.seconds/60)} min · ${state.refresh_preview.reason}.`:'';
  $('displayOpen').disabled=false;renderSchedule();$('notice').textContent='Your server is ready.';
  const container=$('programChoices');container.replaceChildren();
  for(const program of state.programs){
    const card=button('',()=>openEditor('program',program.id)),icon=element('span',undefined,'icon');card.className='program'+(chosen===program.id?' active':'');card.setAttribute('aria-label','Open '+program.name);icon.append(svgIcon(icons[program.id]));
    const content=element('div');content.append(element('h3',program.name),element('p',program.description));
    const arrow=element('span',undefined,'chevron');arrow.append(svgIcon('chevron'));card.append(icon,content,arrow);container.append(card);
  }
  renderReminders();
}
function field(root,key,labelText,value,type='text',choices=null){
  const wrapper=element('p'),label=element('label',labelText+' ');let input;
  if(choices){input=element('select');for(const [val,text] of choices){const option=element('option',text);option.value=val;input.append(option)}}
  else{input=element('input');input.type=type;if(type==='number'){input.min='1';input.max='1440';input.step='1'}if(type==='text')input.maxLength=key==='subtitle'?100:60}
  input.dataset.option=key;if(type==='checkbox')input.checked=value;else input.value=value;
  label.append(input);wrapper.append(label);root.append(wrapper);return input;
}
function openEditor(kind,program=state.active_program){
  editingKind=kind;editingProgram=program;$('error').textContent='';
  $('title').textContent=kind==='display'?'Display options':nameFor(program);
  $('displayFields').hidden=kind!=='display';$('programFields').hidden=kind!=='program'||localPrograms.has(program);$('customProgramFields').hidden=kind!=='program'||!localPrograms.has(program);
  const a=state.adaptive_refresh;$('refreshMode').value=state.refresh_mode;$('minutes').value=state.device_refresh_seconds/60;$('adaptiveMin').value=a.min_seconds/60;$('adaptiveMax').value=a.max_seconds/60;$('quietEnabled').checked=a.quiet_enabled;$('quietStart').value=a.quiet_start;$('quietEnd').value=a.quiet_end;
  $('serverMinutes').value=state.server_refresh_seconds/60;$('temperatureDelta').value=a.temperature_delta_c;$('precipitationPercent').value=a.precipitation_percent;$('windDelta').value=a.wind_delta_kmh;
  $('weatherThresholds').hidden=program!=='simple-weather';$('scheduleFields').hidden=program!=='weather-cal';$('advisories').checked=state.advisories;$('zone').textContent='Timezone: '+state.timezone;$('schedule').replaceChildren();
  for(const page of state.programs.find(p=>p.id==='weather-cal').pages){const row=element('div',undefined,'row'),label=element('label'),check=element('input'),time=element('input');check.type='checkbox';check.checked=state.enabled_pages.includes(page);check.dataset.page=page;label.append(check,document.createTextNode(page));time.type='time';time.value=Object.keys(state.page_schedule).find(t=>state.page_schedule[t]===page)||defaults[page];time.setAttribute('aria-label',page+' start time');time.disabled=!check.checked;check.onchange=()=>time.disabled=!check.checked;row.append(label,time);$('schedule').append(row)}
  if(kind==='program'&&localPrograms.has(program))renderCustomFields(program);
  $('artworkSection').hidden=kind!=='program';$('editor').showModal();if(kind==='program')loadArtwork(program);
}
const iconChoices=[['star','Star'],['heart','Heart'],['plane','Travel'],['gift','Gift'],['calendar','Calendar']];
function renderCustomFields(program){
  const root=$('customProgramFields');root.replaceChildren();const o=state.app_settings[program];
  if(program==='clock-calendar'){
    field(root,'title','Heading',o.title);field(root,'format','Time format',o.format,'text',[['12','12 hour'],['24','24 hour']]);field(root,'week_start','Week begins',o.week_start,'text',[['monday','Monday'],['sunday','Sunday']]);field(root,'refresh_minutes','Update every (minutes)',o.refresh_minutes,'number');root.append(element('p','The clock shows the time at the last fetch. Shorter intervals use more battery.','muted'));
  }else if(program==='photo-frame'){
    field(root,'minutes','Show each picture for (minutes)',o.minutes,'number');field(root,'fit','Picture fit',o.fit,'text',[['contain','Fit entire picture'],['cover','Fill frame (crop edges)']]);const border=field(root,'border','Frame border (pixels)',o.border,'number');border.min=0;border.max=60;field(root,'caption','Show picture name',o.caption,'checkbox');field(root,'dither','Use black-and-white dithering',o.dither,'checkbox');root.append(element('p','Pictures rotate in upload order. Each gets its full display time; opening previews never advances the slideshow.','muted'));
  }else if(program==='countdown'){
    field(root,'title','Event title',o.title);field(root,'date','Event date',o.date,'date');field(root,'icon','Icon',o.icon,'text',iconChoices);field(root,'image','Picture instead of icon',o.image,'text',[['','Use the icon'],...pictures.map(p=>[p.id,p.name])]);field(root,'subtitle','Subtitle',o.subtitle);field(root,'complete','Message on the day',o.complete);field(root,'refresh_minutes','Update every (minutes)',o.refresh_minutes,'number');root.append(element('p','After the date, the display counts days since the event.','muted'));
  }else if(program==='daylight'){
    field(root,'title','Heading',o.title);field(root,'format','Time format',o.format,'text',[['12','12 hour'],['24','24 hour']]);field(root,'refresh_minutes','Update every (minutes)',o.refresh_minutes,'number');root.append(element('p','Uses your server location and timezone: '+state.timezone+'. Sunrise, sunset and daylight duration come from Open-Meteo.','muted'));
  }
  if(program==='photo-frame'){
    const controls=element('details',undefined,'technical');controls.append(element('summary','Slideshow options'));
    while(root.firstChild)controls.append(root.firstChild);
    renderLibrary(root,program);root.append(controls);
  }else if(program==='countdown')renderLibrary(root,program);

}
function loadArtwork(program=editingProgram,image){
  const preview=$('programArtwork');preview.hidden=true;$('artworkStatus').textContent='Loading…';preview.setAttribute('aria-busy','true');
  preview.onload=()=>{preview.hidden=false;preview.removeAttribute('aria-busy');$('artworkStatus').textContent=''};
  preview.onerror=()=>{preview.hidden=true;preview.removeAttribute('aria-busy');$('artworkStatus').textContent='Preview unavailable. Try refreshing in a moment.'};
  preview.src='/api/program/preview.png?program='+encodeURIComponent(program)+(image?'&image='+image:'')+'&t='+Date.now();
}
$('reloadArtwork').onclick=()=>loadArtwork();
function renderLibrary(root,program){
  root.append(element('h3','Your pictures'));
  const upload=element('input');upload.type='file';upload.accept='image/jpeg,image/png,image/webp,image/heic,image/heif,.heic,.heif';upload.multiple=true;upload.hidden=true;upload.setAttribute('aria-label','Upload pictures');
  const add=button('Add photos',()=>upload.click());add.className='upload-button';
  const status=element('p','iPhone HEIC, JPEG, PNG or WebP · up to 12 MB each. Tap a picture to see it in the frame.','muted');status.setAttribute('role','status');
  const gallery=element('div',undefined,'gallery');
  const fillGallery=()=>{gallery.replaceChildren();if(!pictures.length)gallery.append(element('p','Your gallery is empty. Add your first photo above.','muted'));for(const picture of pictures){
    const tile=element('div',undefined,'gallery-tile'),img=element('img');img.src='/api/media/'+picture.id;img.alt=picture.name;img.loading='lazy';
    const choose=button('',()=>{gallery.querySelectorAll('.selected').forEach(t=>t.classList.remove('selected'));tile.classList.add('selected');const select=root.querySelector('[data-option="image"]');if(select)select.value=picture.id;loadArtwork('photo-frame',picture.id);$('artworkSection').scrollIntoView({block:'nearest'})});choose.className='photo-select';choose.setAttribute('aria-label','Preview '+picture.name);choose.append(img);
    const remove=iconButton('trash','Delete '+picture.name,async()=>{remove.disabled=true;try{const result=await api('/api/media/delete',{id:picture.id});pictures=result.pictures;state=result.settings;fillGallery();syncImageOptions(root);loadArtwork(program)}catch(error){status.textContent=error.message}finally{remove.disabled=false}});
    const actions=element('div',undefined,'row');actions.append(element('small',picture.width+' × '+picture.height,'muted'),remove);tile.append(choose,element('p',picture.name),actions);gallery.append(tile)
  }};
  upload.onchange=async()=>{add.disabled=true;try{let index=0;for(const file of upload.files){status.textContent='Uploading '+(++index)+' of '+upload.files.length+'…';if(file.size>12*1024*1024)throw Error(file.name+' is larger than 12 MB');const response=await fetch('/api/media',{method:'POST',headers:{'Content-Type':file.type||'application/octet-stream','X-File-Name':encodeURIComponent(file.name)},body:file});const data=await response.json();if(!response.ok)throw Error(data.error);pictures=data.pictures;fillGallery();syncImageOptions(root)}status.textContent='Photos added. Tap a picture to preview it.';loadArtwork(program)}catch(error){status.textContent=error.message}finally{add.disabled=false;upload.value=''}};
  root.append(upload,add,status,gallery);fillGallery();
}
function syncImageOptions(root){const select=root.querySelector('[data-option="image"]');if(!select)return;const selected=select.value;select.replaceChildren();for(const [id,name] of [['','Use the icon'],...pictures.map(p=>[p.id,p.name])]){const option=element('option',name);option.value=id;select.append(option)}select.value=pictures.some(p=>p.id===selected)?selected:''}
$('displayOpen').onclick=()=>openEditor('display');$('close').onclick=$('cancel').onclick=()=>$('editor').close();
$('form').onsubmit=async event=>{
  event.preventDefault();$('error').textContent='';const data=settingsData();
  try{
    if(editingKind==='display'){
      data.device_refresh_seconds=Math.round(Number($('minutes').value)*60);data.refresh_mode=$('refreshMode').value;
      Object.assign(data.adaptive_refresh,{min_seconds:Number($('adaptiveMin').value)*60,max_seconds:Number($('adaptiveMax').value)*60,quiet_enabled:$('quietEnabled').checked,quiet_start:$('quietStart').value,quiet_end:$('quietEnd').value});

    }else if(localPrograms.has(editingProgram)){
      for(const input of $('customProgramFields').querySelectorAll('[data-option]'))data.app_settings[editingProgram][input.dataset.option]=input.type==='checkbox'?input.checked:input.type==='number'?Number(input.value):input.value;
    }else{
      data.server_refresh_seconds=Number($('serverMinutes').value)*60;
      if(editingProgram==='simple-weather')Object.assign(data.adaptive_refresh,{temperature_delta_c:Number($('temperatureDelta').value),precipitation_percent:Number($('precipitationPercent').value),wind_delta_kmh:Number($('windDelta').value)});
      else{data.enabled_pages=[];data.page_schedule={};data.advisories=$('advisories').checked;for(const row of $('schedule').children){const check=row.querySelector('input[type=checkbox]'),time=row.querySelector('input[type=time]').value;if(check.checked){if(!time||data.page_schedule[time])throw Error('Give each enabled page a different start time.');data.enabled_pages.push(check.dataset.page);data.page_schedule[time]=check.dataset.page}}}
    }
    $('save').disabled=true;busy=true;state=await api('/api/settings',data);render();if(editingKind==='program'){loadArtwork();$('error').textContent='Saved. Preview updated below.'}else $('editor').close();$('notice').textContent='Saved. Your Nook receives the changes on its next fetch.';
  }catch(error){$('error').textContent=error.message}finally{$('save').disabled=false;busy=false}
};
function addProgramTime(time='12:00',program='simple-weather'){const row=element('div',undefined,'row');row.style.marginTop='12px';const input=element('input');input.type='time';input.value=time;input.setAttribute('aria-label','Program start time');const select=element('select');select.setAttribute('aria-label','Scheduled program');for(const p of state.programs){const option=element('option',p.name);option.value=p.id;select.append(option)}select.value=program;row.append(input,select,iconButton('trash','Remove schedule time',()=>{row.remove();scheduleDirty=true}));$('programScheduleRows').append(row)}
function renderSchedule(){
  $('scheduleNow').textContent='Now: '+nameFor(state.current_program)+' · '+state.timezone;
  if(scheduleDirty)return;
  $('programScheduleRows').replaceChildren();
  const schedule=state.program_schedule_enabled?state.program_schedule:{'00:00':state.active_program};
  for(const [time,program] of Object.entries(schedule).sort())addProgramTime(time,program);
}
$('programScheduleRows').oninput=$('programScheduleRows').onchange=()=>{scheduleDirty=true;$('scheduleStatus').textContent='Unsaved schedule changes'};
$('addProgramTime').onclick=()=>{if($('programScheduleRows').children.length<12){addProgramTime();scheduleDirty=true}};
$('saveProgramSchedule').onclick=async()=>{
  const schedule={};$('scheduleStatus').textContent='';
  try{
    for(const row of $('programScheduleRows').children){const time=row.querySelector('input').value;if(!time||schedule[time])throw Error('Give every row a different start time.');schedule[time]=row.querySelector('select').value}
    if(!Object.keys(schedule).length)throw Error('Add at least one program.');
    busy=true;$('saveProgramSchedule').disabled=true;
    state=await api('/api/settings',{...settingsData(),program_schedule_enabled:true,program_schedule:schedule});scheduleDirty=false;render();$('scheduleStatus').textContent='Schedule saved. The Nook receives the new timing on its next fetch.';
  }catch(error){$('scheduleStatus').textContent=error.message}finally{busy=false;$('saveProgramSchedule').disabled=false}
};
$('resetDisplay').onclick=async()=>{const button=$('resetDisplay');button.disabled=true;$('resetStatus').textContent='Connecting to the Nook…';try{$('resetStatus').textContent=(await api('/api/display/reset',{})).message}catch(error){$('resetStatus').textContent=error.message}finally{button.disabled=false}};
function openReminder(record={}){
  $('reminderId').value=record.id||'';$('reminderName').value=record.title||'';$('reminderMessage').value=record.message||'';$('reminderWhen').value=record.when||'';$('reminderMinutes').value=record.minutes||15;$('reminderIcon').value=record.icon||'calendar';$('reminderRepeat').value=record.repeat||'none';$('reminderError').textContent='';$('reminderTitle').textContent=record.id?'Edit reminder':'Add reminder';$('reminderZone').textContent='Timezone: '+state.timezone+'. Repeats keep this local time. Missing daylight-saving times are skipped; repeated times run once.';$('reminderEditor').showModal();
}
function renderReminders(){
  const root=$('reminderList');root.replaceChildren();for(const reminder of [...state.reminders].sort((a,b)=>(a.occurrence_at??Infinity)-(b.occurrence_at??Infinity))){
    const row=element('div',undefined,'reminder-item'),now=Date.now()/1000,end=reminder.at+reminder.minutes*60;
    row.append(element('strong',reminder.title),element('p',`${reminder.occurrence_at?timeAt(reminder.occurrence_at):timeAt(reminder.at)} · ${reminder.minutes} minutes · ${{none:'Once',daily:'Daily',weekdays:'Weekdays',weekly:'Weekly'}[reminder.repeat||'none']} · ${reminder.showing?'Showing now':reminder.occurrence_at?'Upcoming':'Finished'}`,'muted'),element('p',reminder.message));
    row.append(iconButton('edit','Edit '+reminder.title,()=>openReminder(reminder)),iconButton('trash','Delete '+reminder.title,async()=>{try{state=await api('/api/reminders',{action:'delete',id:reminder.id});renderReminders()}catch(error){$('notice').textContent=error.message}}));root.append(row);
  }if(!state.reminders.length)root.append(element('p','No reminders yet.','muted'));
  const next=activity?.next_fetch,early=next&&state.reminders.some(r=>r.occurrence_at>Date.now()/1000&&r.occurrence_at<next);
  $('reminderTiming').textContent=early?`A reminder starts before the Nook’s next expected fetch (${timeAt(next)}). Wake the Nook so it can receive the new timer; otherwise that reminder may be late or missed.`:next?`Next expected connection: ${timeAt(next)}. Add reminders before this connection, or wake the Nook to receive a new timer.`:'The Nook learns about reminders on its next fetch. Wake it after adding a near-term reminder.';
}
$('addReminder').onclick=()=>openReminder();$('reminderClose').onclick=$('reminderCancel').onclick=()=>$('reminderEditor').close();
$('reminderForm').onsubmit=async event=>{event.preventDefault();$('reminderSave').disabled=true;busy=true;try{state=await api('/api/reminders',{action:'upsert',id:$('reminderId').value,title:$('reminderName').value,message:$('reminderMessage').value,when:$('reminderWhen').value,minutes:Number($('reminderMinutes').value),icon:$('reminderIcon').value,repeat:$('reminderRepeat').value});renderReminders();$('reminderEditor').close()}catch(error){$('reminderError').textContent=error.message}finally{$('reminderSave').disabled=false;busy=false}};
async function refreshActivity(){
  try{
    activity=await api('/api/display/status');if(!state)return;
    if(!busy&&!$('editor').open&&!$('reminderEditor').open){state=await api('/api/settings');render()}
    const data=activity,battery=data.battery;
    $('batteryLevel').textContent=battery?`${battery.percent}%${battery.charging?' · plugged in':''}`:'Waiting for device report';
    $('batteryReport').textContent=battery?`Reported ${timeAt(battery.at)}. `+(battery.days_remaining!==null?`Estimated ${battery.days_remaining} days remaining at the observed discharge rate.`:battery.charging?'Unplug to measure discharge.':'Learning discharge rate: needs at least 24 hours and a 3% drop.'):'Waiting for a battery reading.';
    $('reliability').textContent=data.reliability+(data.renderer_retrying?' · retaining last good image':'');
    $('failureReport').textContent=`Device failures reported: ${data.device_failures??'unknown'}. Transfer failures today: ${data.days[0].failures.length}.`;
    $('savingsReport').textContent=data.days.map((day,i)=>`${i?'Yesterday':'Today'}: ${day.count} fetches vs ${day.hourly_baseline} hourly baseline (${Math.abs(day.fetches_avoided)} ${day.fetches_avoided>=0?'fewer':'more'}).`).join(' ');
    $('displayPreview').hidden=!data.has_preview;
    $('previewTime').textContent=data.has_preview?`Fetched ${timeAt(data.last_fetch.at)}${data.image.program?' · '+nameFor(data.image.program):''}. Exact image delivered to the Nook.`:'The exact preview will appear after the Nook’s next successful fetch.';
    const hash=data.last_fetch?.image_hash;if(data.has_preview&&$('displayPreview').dataset.hash!==hash){$('displayPreview').dataset.hash=hash;$('displayPreview').src='/api/display/preview.png?image='+hash}
    $('lastFetch').textContent=data.last_fetch?timeAt(data.last_fetch.at):'No fetch recorded yet';$('nextFetch').textContent=data.next_fetch?timeAt(data.next_fetch)+(Date.now()/1000>data.next_fetch?' · overdue':''):'After the first fetch';$('todayCount').textContent=data.days[0].count;
    for(let i=0;i<2;i++){const prefix=i===0?'today':'yesterday',day=data.days[i];$(prefix+'Heading').textContent=`${i?'Yesterday':'Today'} · ${day.count} updates`;const list=$(prefix+'Events');list.replaceChildren();for(const event of day.events){const item=element('li',timeAt(event.at,false)),detail=element('small',`Next in ${Math.round(event.seconds/60)} min · ${event.reason}`);item.append(detail);list.append(item)}for(const failure of day.failures)list.append(element('li',timeAt(failure.at,false)+' · '+failure.reason));if(!list.children.length)list.append(element('li','No recorded fetches.'))}
    $('trackingSince').textContent=`Tracking since ${timeAt(data.started_at)} · ${state.timezone}. Earlier fetches are not included.`;$('activityStatus').textContent='';renderReminders();
  }catch(error){$('activityStatus').textContent='Fetch history unavailable. Retrying shortly.'}
}
Promise.all([api('/api/settings'),api('/api/media')]).then(([settings,media])=>{state=settings;pictures=media.pictures;render();refreshActivity()}).catch(error=>$('notice').textContent=error.message);
setInterval(refreshActivity,30000);

for(const id of ["close","reminderClose"]){$(id).replaceChildren(svgIcon("close"));$(id).classList.add("icon-button")}
