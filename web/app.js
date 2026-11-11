const $ = (id) => document.getElementById(id);
const state = {page:'home', settings:{provider:'osm',map_style:'roadmap',view_mode:'basic',motion:true}, journey:null, map:null, tileLayer:null, routeLayer:null, markers:[], googleMap:null, googleLine:null, googleMarkers:[], mapReadyPromise:null, mapGeneration:0, activeFilter:'All', reports:[], profile:{}, mapInitialized:false, tileErrors:0, reportLocationSelection:null, reportLocationCandidates:[], reportPickerMap:null, reportPickerMarker:null, resolvingReportId:null};
const api = async (url, options={}) => { const r=await fetch(url,{headers:{'Content-Type':'application/json',...(options.headers||{})},...options}); const data=await r.json().catch(()=>({detail:'Unexpected server response'})); if(!r.ok) throw new Error(data.detail||'Request failed'); return data; };
function toast(msg){const t=$('toast');t.textContent=msg;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2800)}
function initials(name){return (name||'S').trim().split(/\s+/).slice(0,2).map(x=>x[0]).join('').toUpperCase()||'S'}
function showPage(name){state.page=name;document.querySelectorAll('.page').forEach(p=>p.classList.toggle('active',p.id===`page-${name}`));document.querySelectorAll('[data-page]').forEach(b=>b.classList.toggle('active',b.dataset.page===name));const labels={home:'Overview',journey:'Plan a journey',community:'Communities',advanced:'Intelligence',profile:'My profile',settings:'Settings'};$('pageCrumb').textContent=labels[name]||name;if(name==='journey')setTimeout(async()=>{try{await ensureActiveMap();await applyMapStyle();resizeActiveMap();if(state.journey)drawJourney(state.journey);}catch(e){showMapError(e.message)}},100);if(name==='community')renderCommunity();if(name==='profile')renderProfile();if(name==='settings')renderSettings();}
document.querySelectorAll('[data-page]').forEach(b=>b.addEventListener('click',()=>showPage(b.dataset.page)));
function setMotion(on){state.settings.motion=on;document.body.classList.toggle('no-motion',!on);$('motionToggle').style.color=on?'var(--mint)':'var(--muted)';if($('motionSetting'))$('motionSetting').checked=on}
function applyMode(mode){state.settings.view_mode=mode;const advancedNav=document.querySelector('[data-page=\"advanced\"]');if(advancedNav)advancedNav.classList.toggle('hidden',mode!=='advanced');document.querySelectorAll('.mode-btn').forEach(x=>x.classList.toggle('active',x.dataset.mode===mode));$('statMode').textContent=mode[0].toUpperCase()+mode.slice(1)}
function updateClock(){const d=new Date();$('clock').textContent=d.toLocaleTimeString([], {hour:'2-digit',minute:'2-digit'});}setInterval(updateClock,10000);updateClock();
function providerName(p){return p==='google'?'GOOGLE MAPS':p==='custom'?'CUSTOM SERVICES':'OPENSTREETMAP'}
async function bootstrap(){try{const d=await api('/api/bootstrap');state.settings={...state.settings,...d.settings};state.profile=d.profile||{};state.reports=d.reports||[];renderAll(d);setMotion(state.settings.motion!==false); }catch(e){toast(e.message)}}
function renderAll(d){const name=state.profile.display_name||'SafeRoute user';$('userName').textContent=name;$('avatarInitial').textContent=initials(name);$('topAvatar').textContent=initials(name);$('navReports').textContent=d.report_count??state.reports.length;$('statReports').textContent=d.report_count??state.reports.length;$('statSaved').textContent=(d.saved_journeys||[]).length;$('statProvider').textContent=state.settings.provider==='google'?'Google':state.settings.provider==='custom'?'Custom':'OSM';$('statProviderDetail').textContent=state.settings.provider==='google'?'Google Maps Platform':state.settings.provider==='custom'?'Configured local endpoints':'Open map ecosystem';applyMode(state.settings.view_mode||'basic');$('homeProvider').textContent=providerName(state.settings.provider);$('serviceName').textContent=state.settings.provider==='google'?'Google Maps':state.settings.provider==='custom'?'Custom map services':'OSM services';renderActivity(state.reports.slice(0,4),$('homeActivity'));renderSaved(d.saved_journeys||[]);renderCommunity();renderProfile();}
function renderActivity(reports,target){if(!reports.length){target.innerHTML='<div class="empty-state compact">No community observations to show yet.</div>';return}target.innerHTML=reports.slice(0,5).map(r=>{const match=r.matched_distance_km!=null?`${esc(r.matched_segment||'Route')} · ${Math.round(r.matched_distance_km*1000)} m from route`:esc(r.status||'Reported');return `<div class="activity-item"><div class="activity-icon">${iconFor(r.category)}</div><div class="activity-copy"><b>${esc(r.category)} · ${esc(r.location)}</b><p>${esc(r.description||'Community observation')}</p></div><span class="activity-meta">${match}</span></div>`}).join('')}
function renderSaved(items){const html=items.length?items.map(x=>`<div class="saved-item" data-origin="${esc(x.start_name)}" data-dest="${esc(x.destination_name)}"><span>↗ ${esc(x.name||`${x.start_name} → ${x.destination_name}`)}</span><span>›</span></div>`).join(''):'<small>No saved journeys yet.</small>';$('savedJourneyList').innerHTML=html;document.querySelectorAll('.saved-item').forEach(el=>el.addEventListener('click',()=>{$('origin').value=el.dataset.origin;$('destination').value=el.dataset.dest;showPage('journey')}));}
function iconFor(c){return ({'Poor Lighting':'◐','Construction':'⚒','Blocked Path':'↗','Road Hazard':'△','Flooding':'≈','Traffic':'⇄'})[c]||'◎'}
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))}
function mapMessage(title,detail,withRetry=false){
 const box=$('map');if(!box)return;
 box.innerHTML=`<div class="map-placeholder"><div class="placeholder-orbit"><span>⌖</span></div><b>${esc(title)}</b><small>${esc(detail||'')}</small>${withRetry?'<button class="small-ghost" id="mapRetry" type="button">Retry map load</button>':''}</div>`;
 if(withRetry){const retry=$('mapRetry');if(retry)retry.addEventListener('click',async()=>{try{await rebuildActiveMap();}catch(e){showMapError(e.message)}})}
}
function showMapError(message){mapMessage('Map could not load',message||'Check your connection and map provider configuration.',true);}
function clearGoogleOverlays(){if(state.googleLine){state.googleLine.setMap(null);state.googleLine=null;}state.googleMarkers.forEach(m=>m.setMap(null));state.googleMarkers=[];}
function destroyActiveMap(){
 state.mapGeneration++;
 clearGoogleOverlays();
 if(state.googleMap&&window.google?.maps){try{google.maps.event.clearInstanceListeners(state.googleMap);}catch(e){}}
 if(state.map){try{state.map.off();state.map.remove();}catch(e){} state.map=null;}
 state.tileLayer=null;state.routeLayer=null;state.markers=[];state.googleMap=null;state.mapInitialized=false;state.tileErrors=0;state.mapReadyPromise=null;
 const box=$('map');if(box)box.innerHTML='';
}
function resizeActiveMap(){requestAnimationFrame(()=>{if(state.map){state.map.invalidateSize({pan:false});}if(state.googleMap&&window.google?.maps){google.maps.event.trigger(state.googleMap,'resize');}});}
function initMap(){
 if(state.settings.provider==='google')return loadGoogleMap();
 if(state.map)return state.map;
 const box=$('map');if(!box)throw new Error('Map workspace is not available.');
 if(!window.L){mapMessage('OpenStreetMap library unavailable','The Leaflet map library did not load. Check your internet connection.',true);throw new Error('Leaflet could not load.');}
 box.innerHTML='';
 state.map=L.map(box,{zoomControl:true,scrollWheelZoom:true}).setView([10.8,78.7],6);
 const url=state.settings.provider==='custom'&&state.settings.custom_tile_url?state.settings.custom_tile_url:'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png';
 state.tileLayer=L.tileLayer(url,{maxZoom:19,attribution:state.settings.provider==='custom'?'Custom map provider':'© OpenStreetMap contributors'}).addTo(state.map);
 state.tileErrors=0;
 state.tileLayer.on('tileerror',()=>{state.tileErrors++;if(state.tileErrors>=3)toast('Some map tiles failed to load. Check the tile service or connection.');});
 state.tileLayer.on('load',()=>{state.tileErrors=0;});
 state.mapInitialized=true;
 $('mapAttribution').textContent=state.settings.provider==='custom'?'Custom map provider':'© OpenStreetMap contributors';
 resizeActiveMap();
 return state.map;
}
async function ensureGoogleApi(){
 if(window.google?.maps)return;
 if(window.__safeRouteGooglePromise)return window.__safeRouteGooglePromise;
 window.__safeRouteGooglePromise=new Promise((resolve,reject)=>{
  const script=document.createElement('script');script.id='saferoute-google-maps-js';script.async=true;script.defer=true;
  const callbackName='__safeRouteGoogleReady';
  window[callbackName]=()=>{delete window[callbackName];resolve();};
  script.src='https://maps.googleapis.com/maps/api/js?key='+encodeURIComponent(window.__safeRouteGoogleKey)+'&v=weekly&loading=async&callback='+callbackName;
  script.onerror=()=>{delete window[callbackName];reject(new Error('Google Maps JavaScript API could not load. Check internet access, API enablement and browser-key referrer restrictions.'));};
  document.head.appendChild(script);
  setTimeout(()=>{if(!window.google?.maps){delete window[callbackName];reject(new Error('Google Maps did not finish loading within 20 seconds.'));}},20000);
 }).catch(error=>{window.__safeRouteGooglePromise=null;throw error;});
 return window.__safeRouteGooglePromise;
}
async function loadGoogleMap(){
 if(state.settings.provider!=='google')return null;
 if(state.googleMap)return state.googleMap;
 if(state.mapReadyPromise)return state.mapReadyPromise;
 const generation=state.mapGeneration;
 const pending=(async()=>{
  mapMessage('Connecting to Google Maps','Loading the map and selected map type…');
  const keyData=await api('/api/map-key');
  if(!keyData.key)throw new Error('The backend did not provide a Google Maps browser key. Confirm Google is saved as the active provider.');
  window.__safeRouteGoogleKey=keyData.key;
  await ensureGoogleApi();
  if(generation!==state.mapGeneration||state.settings.provider!=='google')return null;
  const box=$('map');if(!box)return null;box.innerHTML='';
  const types={roadmap:google.maps.MapTypeId.ROADMAP,satellite:google.maps.MapTypeId.SATELLITE,terrain:google.maps.MapTypeId.TERRAIN,hybrid:google.maps.MapTypeId.HYBRID};
  state.googleMap=new google.maps.Map(box,{center:{lat:10.8,lng:78.7},zoom:6,mapTypeId:types[state.settings.map_style]||types.ROADMAP,tilt:0,streetViewControl:false,mapTypeControl:false,fullscreenControl:true,gestureHandling:'greedy'});
  state.googleMap.addListener('maptypeid_changed',()=>{const current=state.googleMap?.getMapTypeId();if(current!==google.maps.MapTypeId.SATELLITE&&current!==google.maps.MapTypeId.HYBRID&&state.googleMap?.getTilt())state.googleMap.setTilt(0);});
  state.mapInitialized=true;$('mapAttribution').textContent='Google Maps Platform';
  resizeActiveMap();
  return state.googleMap;
 })();
 state.mapReadyPromise=pending;
 try{return await pending;}catch(e){if(generation===state.mapGeneration)showMapError(e.message);throw e;}finally{if(state.mapReadyPromise===pending)state.mapReadyPromise=null;}
}
async function ensureActiveMap(){if(state.settings.provider==='google')return loadGoogleMap();return initMap();}
async function rebuildActiveMap(){destroyActiveMap();await ensureActiveMap();resizeActiveMap();if(state.journey)drawJourney(state.journey);}
async function applyMapStyle(){
 const style=state.settings.map_style||'roadmap';
 if($('mapStyle'))$('mapStyle').value=style;
 document.querySelectorAll('.style-choice').forEach(b=>b.classList.toggle('selected',b.dataset.style===style));
 if(state.settings.provider==='google'){
  const map=state.googleMap||await loadGoogleMap();
  if(!map)return;
  const types={roadmap:google.maps.MapTypeId.ROADMAP,satellite:google.maps.MapTypeId.SATELLITE,terrain:google.maps.MapTypeId.TERRAIN,hybrid:google.maps.MapTypeId.HYBRID};
  map.setMapTypeId(types[style]||types.roadmap);
  $('mapAttribution').textContent='Google Maps Platform';
 }else{
  $('mapAttribution').textContent=state.settings.provider==='custom'?'Custom map provider':'© OpenStreetMap contributors';
 }
}
function settingsProviderChoice(){return document.querySelector('input[name="provider"]:checked')?.value||state.settings.provider;}
function updateStyleAvailability(){const available=settingsProviderChoice()==='google';document.querySelectorAll('.style-choice').forEach(b=>{b.disabled=!available;b.title=available?'Select a Google Maps map type':'Select Google Maps Platform to use these map types';});if($('mapStyle'))$('mapStyle').disabled=state.settings.provider!=='google';}
$('mapStyle').addEventListener('change',async e=>{if(state.settings.provider!=='google'){e.target.value=state.settings.map_style||'roadmap';toast('Choose Google Maps Platform to use these map styles.');return;}state.settings.map_style=e.target.value;try{await applyMapStyle();state.settings=await api('/api/settings',{method:'PUT',body:JSON.stringify(state.settings)});toast('Google map style saved');}catch(error){toast(error.message);}});
$('tiltBtn').addEventListener('click',()=>{if(state.googleMap){const type=state.googleMap.getMapTypeId();if(type!==google.maps.MapTypeId.SATELLITE&&type!==google.maps.MapTypeId.HYBRID){toast('Switch to Satellite or Hybrid before enabling perspective tilt.');return;}const tilt=state.googleMap.getTilt()||0;state.googleMap.setTilt(tilt?0:45);state.googleMap.setHeading(tilt?0:25);toast(tilt?'Map tilt disabled':'Perspective tilt enabled');}else toast('Tilt is available with Google Maps. OSM 3D requires a compatible 3D tile provider.');});
$('layersBtn').addEventListener('click',()=>toast('Community and hotspot layers appear after a route is analysed.'));
window.gm_authFailure=()=>showMapError('Google rejected the browser key. Check its Maps JavaScript API restriction and allowed localhost referrer.');
function drawJourney(data){
 state.journey=data;
 if(state.settings.provider==='google'){
  if(!state.googleMap){ensureActiveMap().then(()=>{if(state.settings.provider==='google'&&state.googleMap)drawJourney(data);}).catch(e=>showMapError(e.message));return;}
  clearGoogleOverlays();
  state.googleLine=new google.maps.Polyline({path:data.route_points.map(p=>({lat:p[0],lng:p[1]})),geodesic:true,strokeColor:'#5bd6b1',strokeOpacity:.95,strokeWeight:5,map:state.googleMap});
  const bounds=new google.maps.LatLngBounds();data.route_points.forEach(p=>bounds.extend({lat:p[0],lng:p[1]}));state.googleMap.fitBounds(bounds,45);
  state.googleMarkers.push(new google.maps.Marker({position:{lat:data.origin.latitude,lng:data.origin.longitude},map:state.googleMap,title:'Start'}));
  state.googleMarkers.push(new google.maps.Marker({position:{lat:data.destination.latitude,lng:data.destination.longitude},map:state.googleMap,title:'Destination'}));
  data.reports.filter(r=>r.latitude!=null&&r.longitude!=null).forEach(r=>state.googleMarkers.push(new google.maps.Marker({position:{lat:r.latitude,lng:r.longitude},map:state.googleMap,title:r.category,icon:{path:google.maps.SymbolPath.CIRCLE,scale:6,fillColor:'#efbd79',fillOpacity:1,strokeColor:'#18272c',strokeWeight:2}})));
  resizeActiveMap();return;
 }
 if(!state.map){try{initMap();}catch(e){showMapError(e.message);return;}}
 if(state.routeLayer)state.map.removeLayer(state.routeLayer);state.markers.forEach(m=>state.map.removeLayer(m));state.markers=[];
 state.routeLayer=L.polyline(data.route_points,{color:'#5bd6b1',weight:5,opacity:.9}).addTo(state.map);
 state.markers.push(L.marker([data.origin.latitude,data.origin.longitude]).addTo(state.map).bindPopup('Journey start'));
 state.markers.push(L.marker([data.destination.latitude,data.destination.longitude]).addTo(state.map).bindPopup('Destination'));
 data.reports.filter(r=>r.latitude!=null&&r.longitude!=null).forEach(r=>state.markers.push(L.circleMarker([r.latitude,r.longitude],{radius:7,color:'#efbd79',fillColor:'#efbd79',fillOpacity:.9}).addTo(state.map).bindPopup(`<b>${esc(r.category)}</b><br>${esc(r.description)}`)));
 state.map.fitBounds(state.routeLayer.getBounds(),{padding:[35,35]});resizeActiveMap();
}
function setDefaultDepartureTime(){const d=new Date(Date.now()+15*60*1000);d.setSeconds(0,0);$('departureTime').value=`${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}T${String(d.getHours()).padStart(2,'0')}:${String(d.getMinutes()).padStart(2,'0')}`;}
function syncDepartureField(){const custom=$('departure').value==='custom';$('departureTimeField').classList.toggle('hidden',!custom);if(custom&&!$('departureTime').value)setDefaultDepartureTime();}
function journeyDeparture(){const v=$('departure').value;if(v==='Now')return 'Now';if(v==='custom'){const dateTime=$('departureTime').value;if(!dateTime)throw new Error('Choose a departure date and time, or select Leave now.');return dateTime.length===16?`${dateTime}:00`:dateTime;}return v;}
async function planJourney(){const origin=$('origin').value.trim(),destination=$('destination').value.trim();$('journeyError').textContent='';if(origin.length<2||destination.length<2){$('journeyError').textContent='Enter both a starting point and destination.';return}const btn=$('calculateBtn');btn.disabled=true;btn.innerHTML='<span class="spinner"></span> Finding route & context…';try{const departure=journeyDeparture();const d=await api('/api/journey',{method:'POST',body:JSON.stringify({origin,destination,departure})});state.journey=d;await ensureActiveMap();drawJourney(d);renderResult(d);toast('Journey intelligence is ready');}catch(e){$('journeyError').textContent=e.message;}finally{btn.disabled=false;btn.innerHTML='Analyse this journey <span>↗</span>';}}
$('departure').addEventListener('change',syncDepartureField);syncDepartureField();$('calculateBtn').addEventListener('click',planJourney);$('homePlan').addEventListener('click',()=>{$('origin').value=$('homeOrigin').value;$('destination').value=$('homeDestination').value;showPage('journey');setTimeout(planJourney,120)});
function renderResult(d){
 $('journeyResult').classList.remove('hidden');$('mapTitle').textContent='Your route · '+d.provider.toUpperCase();$('resultRouteName').textContent=`${$('origin').value} → ${$('destination').value}`;$('resultMeta').textContent=`${d.provider.toUpperCase()} · ${d.traffic_aware?'Traffic-aware estimate':'Standard route estimate'} · ${d.report_count} matched observations`;$('resultDistance').textContent=`${d.distance_km} km`;$('resultDuration').textContent=`${d.duration_min} min`;$('resultScore').textContent=`${d.score}/10`;$('resultConfidence').textContent=d.confidence;$('scoreValue').textContent=d.score;$('assessmentText').textContent=d.assessment;$('briefingText').textContent=d.briefing?.summary||'No additional briefing available.';$('scoreRing').style.borderColor=d.score>7?'#f18c83':d.score>3?'#efbd79':'#4ebd9b';
 $('hotspotList').innerHTML=(d.hotspots||[]).length?d.hotspots.map(h=>`<div class="hotspot"><b>${esc(h.segment||h.name||'Route segment')}</b><span>${h.report_count||h.count||0} report(s)</span></div>`).join(''):'<div class="empty-state compact">No distinct hotspots in available reports.</div>';
 renderActivity(d.reports||[],$('routeReports'));
 const coverage=d.location_coverage||{};const total=coverage.total_observations??0;const geo=coverage.geotagged_observations??0;const matchedGeo=coverage.matched_geotagged_observations??0;const outside=coverage.unmatched_geotagged_observations??0;const unverified=coverage.unverified_locations??0;const radius=coverage.match_radius_m??300;
 $('locationCoverage').textContent=`${d.report_count} observations matched this route. ${matchedGeo} of ${geo} geotagged reports were within ${radius} m; ${outside} geotagged reports were outside the corridor, and ${unverified} of ${total} total reports still need a confirmed location.`;
 $('advScore').innerHTML=`${d.score}<small>/10</small>`;$('advML').innerHTML=`${d.ml_risk}<small>/10</small>`;$('advReports').textContent=d.report_count;$('advGeotagged').textContent=geo;$('advUnverified').textContent=unverified;$('advConfidence').textContent=d.confidence;$('advHotspots').textContent=(d.hotspots||[]).length;$('mlFactors').innerHTML=(d.ml_factors||[]).map(f=>`<div class="factor">✳ ${esc(f)}</div>`).join('')||'<div class="empty-state">No model factors available.</div>';
}
$('saveJourneyBtn').addEventListener('click',async()=>{if(!state.journey)return;try{await api('/api/journeys/save',{method:'POST',body:JSON.stringify({origin:$('origin').value,destination:$('destination').value,start_coordinates:[state.journey.origin.latitude,state.journey.origin.longitude],destination_coordinates:[state.journey.destination.latitude,state.journey.destination.longitude],distance_km:state.journey.distance_km,duration_min:state.journey.duration_min})});toast('Journey saved to your profile');const d=await api('/api/bootstrap');renderSaved(d.saved_journeys||[]);$('statSaved').textContent=(d.saved_journeys||[]).length;}catch(e){toast(e.message)}});
function renderCommunity(){
 const list=state.reports.filter(r=>(state.activeFilter==='All'||r.category===state.activeFilter)&&(`${r.location} ${r.description} ${r.category}`).toLowerCase().includes(($('reportSearch')?.value||'').toLowerCase()));
 $('communityTotal').textContent=list.length;$('communitySource').textContent='LOCAL';
 $('communityFeed').innerHTML=list.length?list.map(r=>{
  const verified=r.location_status==='verified'||(r.latitude!=null&&r.longitude!=null);
  return `<article class="report-card"><div class="report-head"><span class="category-chip">${iconFor(r.category)} ${esc(r.category)}</span><span class="severity">${['','LOW','MODERATE','HIGH'][r.severity]||'MODERATE'} SEVERITY</span></div><h3>${esc(r.location)}</h3><p>${esc(r.description||'Community observation')}</p><div class="report-verification ${verified?'verified':'unverified'}">${verified?'✓ LOCATION VERIFIED':'! LOCATION NEEDS CONFIRMATION'}</div><div class="report-foot"><span>${esc(r.author||'Community member')} · ${esc(r.timestamp||'')}</span><span class="status-chip">${esc(r.status||'Reported')}</span></div>${!verified?`<button class="text-btn resolve-location-btn" data-resolve-location="${r.id}">Resolve location ↗</button>`:''}</article>`;
 }).join(''):'<div class="empty-state" style="grid-column:1/-1">No matching observations. Be the first to share useful local context.</div>';
 document.querySelectorAll('[data-resolve-location]').forEach(b=>b.addEventListener('click',()=>openResolveLocation(Number(b.dataset.resolveLocation))));
}
document.querySelectorAll('.filter').forEach(b=>b.addEventListener('click',()=>{document.querySelectorAll('.filter').forEach(x=>x.classList.remove('active'));b.classList.add('active');state.activeFilter=b.dataset.filter;renderCommunity()}));$('reportSearch').addEventListener('input',renderCommunity);
function resetReportLocationPicker(){
 state.reportLocationSelection=null;state.reportLocationCandidates=[];state.resolvingReportId=null;
 $('reportLocation').value='';$('reportLocationSuggestions').innerHTML='';$('reportLocationSuggestions').classList.add('hidden');$('reportLocationStatus').textContent='Location not selected yet.';$('reportLocationCoords').textContent='';$('reportLocationCoords').classList.add('hidden');$('reportPinMap').classList.add('hidden');
 if(state.reportPickerMarker&&state.reportPickerMap){state.reportPickerMap.removeLayer(state.reportPickerMarker);state.reportPickerMarker=null;}
 $('reportDetails').classList.remove('hidden');$('reportModalTitle').textContent='Share what you noticed.';$('reportModalIntro').textContent='Useful local context helps other travellers make informed decisions. Confirm the exact place so SafeRoute can match it to nearby journeys.';$('submitReport').textContent='Submit observation ↗';$('reportCategory').value='Poor Lighting';$('reportSeverity').value='2';$('reportDescription').value='';
}
function openReportModal(){resetReportLocationPicker();$('reportMessage').textContent='';$('reportModal').classList.remove('hidden');$('reportLocation').focus();}
function closeReport(){$('reportModal').classList.add('hidden');$('reportMessage').textContent='';}
function updateReportLocationStatus(selection){
 state.reportLocationSelection=selection;
 const lat=Number(selection.latitude),lon=Number(selection.longitude);
 $('reportLocationStatus').textContent=`Location confirmed · ${selection.provider||'manual pin'}`;
 $('reportLocationCoords').textContent=`Coordinates: ${lat.toFixed(6)}, ${lon.toFixed(6)}`;$('reportLocationCoords').classList.remove('hidden');
 if(state.reportPickerMap){const point=[lat,lon];state.reportPickerMap.setView(point,16);if(state.reportPickerMarker)state.reportPickerMarker.setLatLng(point);else state.reportPickerMarker=L.marker(point).addTo(state.reportPickerMap);}
}
function selectReportLocation(candidate){
 const name=candidate.display_name||candidate.formatted_address||'Selected location';
 $('reportLocation').value=name;
 updateReportLocationStatus({...candidate,display_name:name,provider:candidate.provider||'geocoder'});
 $('reportLocationSuggestions').classList.add('hidden');$('reportLocationSuggestions').innerHTML='';
}
let reportSearchTimer=null;
$('reportLocation').addEventListener('input',()=>{
 state.reportLocationSelection=null;$('reportLocationStatus').textContent='Choose a suggested result or drop a map pin.';$('reportLocationCoords').classList.add('hidden');
 const q=$('reportLocation').value.trim();clearTimeout(reportSearchTimer);$('reportLocationSuggestions').classList.add('hidden');
 if(q.length<3)return;
 reportSearchTimer=setTimeout(async()=>{
  try{
   const items=await api('/api/location-search?q='+encodeURIComponent(q));state.reportLocationCandidates=items||[];
   const list=$('reportLocationSuggestions');
   if(!state.reportLocationCandidates.length){list.innerHTML='<div class="suggestion-empty">No matching places. Try a nearby landmark or drop a pin.</div>';list.classList.remove('hidden');return;}
   list.innerHTML=state.reportLocationCandidates.map((x,i)=>`<button type="button" class="location-suggestion" data-location-choice="${i}"><b>${esc(x.display_name||x.formatted_address||'Location')}</b><small>${esc(x.area||x.formatted_address||x.category||x.provider||'')}</small></button>`).join('');list.classList.remove('hidden');
   list.querySelectorAll('[data-location-choice]').forEach(b=>b.addEventListener('click',()=>{const item=state.reportLocationCandidates[Number(b.dataset.locationChoice)];if(item)selectReportLocation(item);}));
  }catch(e){$('reportLocationStatus').textContent='Location search unavailable. You can still place a manual pin.';}
 },450);
});
function initReportPinMap(){
 if(state.reportPickerMap||!window.L)return;
 const center=state.reportLocationSelection?[state.reportLocationSelection.latitude,state.reportLocationSelection.longitude]:[10.8,78.7];
 state.reportPickerMap=L.map('reportPinMap',{zoomControl:true,scrollWheelZoom:true}).setView(center,state.reportLocationSelection?16:6);
 L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',{maxZoom:19,attribution:'© OpenStreetMap contributors'}).addTo(state.reportPickerMap);
 state.reportPickerMap.on('click',event=>{
  const lat=event.latlng.lat,lon=event.latlng.lng;
  const label=$('reportLocation').value.trim()||`Pinned location (${lat.toFixed(5)}, ${lon.toFixed(5)})`;
  $('reportLocation').value=label;
  updateReportLocationStatus({latitude:lat,longitude:lon,display_name:label,place_id:null,provider:'manual'});
 });
 if(state.reportLocationSelection){const point=[state.reportLocationSelection.latitude,state.reportLocationSelection.longitude];state.reportPickerMarker=L.marker(point).addTo(state.reportPickerMap);}
}
function toggleReportPinMap(){
 const box=$('reportPinMap');const opening=box.classList.contains('hidden');box.classList.toggle('hidden',!opening);
 if(opening){initReportPinMap();setTimeout(()=>state.reportPickerMap?.invalidateSize(),80);}
}
function openResolveLocation(reportId){
 const report=state.reports.find(r=>Number(r.id)===Number(reportId));if(!report)return;
 resetReportLocationPicker();state.resolvingReportId=reportId;$('reportDetails').classList.add('hidden');$('reportModalTitle').textContent='Confirm this observation location.';$('reportModalIntro').textContent='This older observation has no verified coordinates. Choose the correct place or manually drop a pin; it will only affect future journey matching after you confirm it.';$('reportLocation').value=report.location||'';$('submitReport').textContent='Save verified location ↗';$('reportModal').classList.remove('hidden');$('reportLocation').focus();$('reportLocation').dispatchEvent(new Event('input'));
}
$('openReport').addEventListener('click',openReportModal);$('closeReport').addEventListener('click',closeReport);$('cancelReport').addEventListener('click',closeReport);$('toggleReportPinMap').addEventListener('click',toggleReportPinMap);
$('submitReport').addEventListener('click',async()=>{
 const location=$('reportLocation').value.trim(),selection=state.reportLocationSelection;
 if(!location){$('reportMessage').textContent='Search for and select a location first.';return;}
 if(!selection||selection.latitude==null||selection.longitude==null){$('reportMessage').textContent='Confirm a location suggestion or drop a pin on the map before continuing.';return;}
 const coords={location,latitude:Number(selection.latitude),longitude:Number(selection.longitude),place_id:selection.place_id||null,location_provider:selection.provider||'manual'};
 const button=$('submitReport');button.disabled=true;
 try{
  if(state.resolvingReportId){await api(`/api/reports/${state.resolvingReportId}/location`,{method:'PATCH',body:JSON.stringify(coords)});toast('Observation location verified');}
  else{
   const payload={...coords,category:$('reportCategory').value,severity:Number($('reportSeverity').value),description:$('reportDescription').value.trim()};
   await api('/api/reports',{method:'POST',body:JSON.stringify(payload)});toast('Observation submitted with verified coordinates');
  }
  closeReport();state.reports=await api('/api/reports');renderCommunity();renderActivity(state.reports.slice(0,4),$('homeActivity'));$('navReports').textContent=state.reports.length;$('statReports').textContent=state.reports.length;
 }catch(e){$('reportMessage').textContent=e.message;}
 finally{button.disabled=false;}
});
function renderProfile(){const p=state.profile||{};const name=p.display_name||'SafeRoute user';$('profileHeading').textContent=name;$('profileAvatar').textContent=initials(name);$('displayName').value=name;$('homeArea').value=p.home_area||'';$('shareName').checked=p.preferences?.share_display_name!==false;$('profileContributions').textContent=p.contributions??0;const saved=p.saved_journeys||[];$('profileSaved').textContent=saved.length;$('profileSavedList').innerHTML=saved.length?saved.map(x=>`<div class="saved-item"><span>↗ ${esc(x.name||`${x.start_name} → ${x.destination_name}`)}</span><button class="text-btn" data-delete="${x.id}">Remove</button></div>`).join(''):'<small>No saved journeys yet.</small>';document.querySelectorAll('[data-delete]').forEach(b=>b.addEventListener('click',async()=>{await api(`/api/journeys/${b.dataset.delete}`,{method:'DELETE'});state.profile=await api('/api/profile');renderProfile();toast('Saved journey removed')}));}
$('saveProfile').addEventListener('click',async()=>{try{state.profile=await api('/api/profile',{method:'PUT',body:JSON.stringify({display_name:$('displayName').value,home_area:$('homeArea').value,preferences:{share_display_name:$('shareName').checked}})});renderProfile();$('userName').textContent=state.profile.display_name;$('avatarInitial').textContent=initials(state.profile.display_name);$('topAvatar').textContent=initials(state.profile.display_name);toast('Profile preferences saved')}catch(e){toast(e.message)}});
function renderSettings(){document.querySelectorAll('input[name="provider"]').forEach(r=>r.checked=r.value===state.settings.provider);document.querySelectorAll('input[name="viewmode"]').forEach(r=>r.checked=r.value===(state.settings.view_mode||'basic'));$('customGeocode').value=state.settings.custom_geocoding_url||'';$('customRoute').value=state.settings.custom_routing_url||'';$('customTiles').value=state.settings.custom_tile_url||'';$('motionSetting').checked=state.settings.motion!==false;$('customFields').classList.toggle('hidden',state.settings.provider!=='custom');document.querySelectorAll('.style-choice').forEach(b=>b.classList.toggle('selected',b.dataset.style===state.settings.map_style));$('mapStyle').value=state.settings.map_style||'roadmap';updateStyleAvailability();$('googleKeyStatus').textContent=state.settings.google_key_available?'Google key detected in private environment. Browser map use requires Maps JavaScript API enabled and localhost referrer restrictions.':'No Google key detected. Add GOOGLE_MAPS_API_KEY to your private .env file to enable Google map services.';}
document.querySelectorAll('input[name="provider"]').forEach(r=>r.addEventListener('change',()=>{$('customFields').classList.toggle('hidden',r.value!=='custom');updateStyleAvailability()}));document.querySelectorAll('.style-choice').forEach(b=>b.addEventListener('click',async()=>{if(b.disabled)return;state.settings.map_style=b.dataset.style;document.querySelectorAll('.style-choice').forEach(x=>x.classList.toggle('selected',x===b));if($('mapStyle'))$('mapStyle').value=state.settings.map_style;if(state.settings.provider==='google'&&state.page==='journey'){try{await applyMapStyle();}catch(e){showMapError(e.message);}}}));$('motionSetting').addEventListener('change',e=>setMotion(e.target.checked));$('motionToggle').addEventListener('click',()=>setMotion(!state.settings.motion));document.querySelectorAll('input[name="viewmode"]').forEach(r=>r.addEventListener('change',()=>applyMode(r.value)));
$('reportDescription').addEventListener('blur',async()=>{const description=$('reportDescription').value.trim();if(description.length<5)return;try{const s=await api('/api/report-suggestion?description='+encodeURIComponent(description));$('reportCategory').value=s.category;$('reportSeverity').value=String(s.severity);$('reportMessage').textContent=`Suggested category: ${s.category} · ${Math.round((s.confidence||0)*100)}% prototype confidence. Please review before submitting.`;$('reportMessage').style.color='var(--muted)'}catch(e){}});
$('saveSettings').addEventListener('click',async()=>{
 const provider=document.querySelector('input[name="provider"]:checked')?.value||'osm';
 const view_mode=document.querySelector('input[name="viewmode"]:checked')?.value||'basic';
 const previousProvider=state.settings.provider;
 const payload={...state.settings,provider,view_mode,custom_geocoding_url:$('customGeocode').value.trim(),custom_routing_url:$('customRoute').value.trim(),custom_tile_url:$('customTiles').value.trim(),map_style:state.settings.map_style||'roadmap',motion:$('motionSetting').checked};
 const button=$('saveSettings');button.disabled=true;button.textContent='Saving settings…';
 try{
  const saved=await api('/api/settings',{method:'PUT',body:JSON.stringify(payload)});
  state.settings=saved;setMotion(state.settings.motion);renderSettings();
  $('settingsMessage').textContent='Settings saved. Your map provider is now '+providerName(provider)+'.';$('settingsMessage').style.color='var(--mint)';
  $('serviceName').textContent=provider==='google'?'Google Maps':provider==='custom'?'Custom map services':'OSM services';$('homeProvider').textContent=providerName(provider);$('statProvider').textContent=provider==='google'?'Google':provider==='custom'?'Custom':'OSM';$('statMode').textContent=view_mode[0].toUpperCase()+view_mode.slice(1);
  if(previousProvider!==provider){destroyActiveMap();if(state.page==='journey'){await ensureActiveMap();if(state.journey)drawJourney(state.journey);resizeActiveMap();}}
  else if(state.page==='journey'){await ensureActiveMap();await applyMapStyle();resizeActiveMap();}
  toast('Map settings updated');
 }catch(e){$('settingsMessage').textContent=e.message;$('settingsMessage').style.color='var(--coral)';}
 finally{button.disabled=false;button.innerHTML='Save map settings <span>↗</span>';}
});
$('nav').addEventListener('click',()=>{});document.querySelectorAll('.mode-btn').forEach(b=>b.addEventListener('click',()=>{applyMode(b.dataset.mode);toast(b.dataset.mode==='advanced'?'Advanced journey controls selected':'Basic journey view selected')}));
bootstrap();
