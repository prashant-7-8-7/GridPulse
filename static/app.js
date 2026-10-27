"use strict";
const $ = (id) => document.getElementById(id);
const state = {rows: [], result: null, selected: 0, busy: false, timer: null,
  source: "Historical sample weather", battery: {capacity_kwh:2000,initial_soc_pct:85,reserve_soc_pct:20,solar_peak_kw:150,inverter_limit_kw:250,efficiency:0.95}};
const escapeHTML = (value) => String(value).replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const num = (value, digits=1) => Number(value).toLocaleString("en-GB", {minimumFractionDigits:digits,maximumFractionDigits:digits});
const hour = (timestamp) => timestamp.slice(11,16);
const day = (timestamp) => new Date(timestamp.slice(0,10)+"T12:00:00Z").toLocaleDateString("en-GB",{day:"numeric",month:"short",year:"numeric",timeZone:"UTC"});

async function api(url, options={}) {
  if (options.method === "POST" && ["/api/forecast", "/api/forecast-csv"].includes(url)) {
    options = {...options, headers:{...options.headers, Prefer:"respond-async"}};
  }
  let response;
  try { response = await fetch(url, options); }
  catch { throw new Error(`Cannot reach ${url}. Keep app.py running and open the server URL, rather than the HTML file directly.`); }
  let data;
  try { data = await response.json(); } catch { throw new Error("The server did not return JSON. Check that app.py is running."); }
  if (!response.ok) throw new Error(data.error || "The request failed.");
  if (response.status === 202 && data.job_id) {
    const jobUrl = "/api/forecast-jobs/" + encodeURIComponent(data.job_id);
    const deadline = Date.now() + 240000;
    while (Date.now() < deadline) {
      await new Promise(resolve => setTimeout(resolve, 1000));
      const job = await api(jobUrl);
      if (job.status === "complete") return job.result;
      if (job.status === "failed") throw new Error(job.error || "The forecast failed.");
    }
    throw new Error("The forecast is taking longer than expected. Please try again shortly.");
  }
  return data;
}
function showError(message) { $("errorBox").textContent=message; $("errorBox").hidden=false; switchTab("overview"); }
function switchTab(name) {
  document.querySelectorAll(".tab-panel").forEach(el=>el.hidden=el.id!==name);
  document.querySelectorAll(".nav-item").forEach(el=>{
    const active=el.dataset.tab===name; el.classList.toggle("active",active);
    if(active) el.setAttribute("aria-current","page"); else el.removeAttribute("aria-current");
  });
}
document.querySelectorAll("[data-tab]").forEach(el=>el.addEventListener("click",()=>switchTab(el.dataset.tab)));
$("rulesButton").addEventListener("click",()=>switchTab("model"));
function stopPlayback() {
  if(state.timer) clearInterval(state.timer);
  state.timer=null; $("playButton").textContent="▶  Play simulation";
}
function dirty() {
  stopPlayback();
  $("sourceNotice").textContent=state.result ? "Inputs changed · displayed plan is from the previous run · run forecast to update" : state.source;
  $("exportBar").hidden=true;
}
function busy(on) {
  state.busy=on;
  for(const id of ["runButton","runTelemetryButton","uploadButton","createScenario","resetData","playButton","batterySettingsButton"]){$(id).disabled=on;}
  document.querySelectorAll("#telemetryBody input, #batteryForm input, #manualStart, #manualTemp, #manualHumidity, #manualSolar").forEach(el=>el.disabled=on);
  $("runButton").textContent=on?"Forecasting…":"↗  Run forecast";
}
function renderTelemetry() {
  $("telemetryBody").innerHTML=state.rows.map((r,i)=>`<tr><td><input aria-label="Timestamp row ${i+1}" data-row="${i}" data-col="timestamp" value="${escapeHTML(r.timestamp)}"></td>${["ambient_temp_c","humidity_pct","solar_irradiance_wm2"].map(c=>`<td><input type="number" step="any" aria-label="${c} row ${i+1}" data-row="${i}" data-col="${c}" value="${r[c]===null?"":escapeHTML(r[c])}"></td>`).join("")}</tr>`).join("");
  $("telemetrySource").textContent=state.source;
}
$("telemetryBody").addEventListener("input",event=>{
  const el=event.target;
  if(el.dataset.row===undefined) return;
  state.rows[Number(el.dataset.row)][el.dataset.col]=el.dataset.col==="timestamp"?el.value:(el.value===""?null:Number(el.value));
  state.source="Manually edited telemetry"; $("telemetrySource").textContent=state.source; dirty();
});

async function runForecast() {
  if(state.busy) return;
  stopPlayback(); busy(true); $("errorBox").hidden=true; $("warningBox").hidden=true;
  try {
    const result=await api("/api/forecast",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({rows:state.rows,battery:state.battery})});
    applyForecast(result); switchTab("overview");
  } catch(error){ showError(error.message); $("exportBar").hidden=true; }
  finally {busy(false);}
}
function applyForecast(result) {
  state.result=result;state.selected=0;
  state.rows=result.rows.map(r=>({timestamp:r.timestamp,ambient_temp_c:r.ambient_temp_c,humidity_pct:r.humidity_pct,solar_irradiance_wm2:r.solar_irradiance_wm2}));
  renderTelemetry();
  const s=result.summary,peak=result.rows.reduce((a,b)=>a.target_demand_kw>b.target_demand_kw?a:b);
  $("peakMetric").textContent=num(s.peak_demand_kw);$("averageMetric").textContent=num(s.average_demand_kw);
  $("storageMetric").textContent=s.storage_hours;$("criticalMetric").textContent=s.critical_hours;
  $("peakTime").textContent=`At ${hour(peak.timestamp)} · ${day(peak.timestamp)}`;
  $("alertFoot").textContent=s.critical_hours?`${s.critical_hours} hour(s) at or above 200 kW`:"No predicted critical overloads";
  $("forecastDate").textContent=`${day(result.rows[0].timestamp)} ${hour(result.rows[0].timestamp)} → ${day(result.rows[23].timestamp)} ${hour(result.rows[23].timestamp)} · local grid time`;
  $("providerBadge").textContent=result.backend==="local"?"●  Local model · demo":"●  QuickML · verified this run";
  $("sourceNotice").textContent=`${state.source} · ${result.backend==="local"?"local model predictions":"QuickML endpoint predictions"} · battery and dispatch are simulated`;
  const warnings=[...result.warnings];
  if(s.critical_hours) warnings.push(`Critical overload forecast in ${s.critical_hours} hour(s).`);
  if(s.battery_shortfall_hours) warnings.push(`Simulated storage cannot meet the requested load in ${s.battery_shortfall_hours} hour(s); ${num(s.unserved_energy_kwh)} kWh unserved. The required dispatch signal is unchanged.`);
  $("warningBox").hidden=!warnings.length;$("warningBox").textContent=warnings.join(" ");
  $("transitionCount").textContent=`${result.transitions.length} signals`;
  $("transitions").innerHTML=result.transitions.map((t,i)=>`<div class="transition-item"><span class="transition-time">${hour(t.timestamp)}</span><span class="tiny-dot ${t.grid_mode==="main_grid"?"main-bg":"green-bg"}"></span><div><strong>${i===0?"Initial signal":"Source transition"}</strong><p>${escapeHTML(t.reason)}</p></div><span class="tag ${t.grid_mode==="main_grid"?"main":"storage"}">${t.grid_mode==="main_grid"?"Main grid":"Storage"}</span></div>`).join("");
  renderTimeline();renderSelected();
  const vals=result.rows.map(r=>r.target_demand_kw),lo=Math.min(...vals),hi=Math.max(...vals);
  $("sparkline").innerHTML=`<path d="${vals.map((v,i)=>`${i?'L':'M'}${i*100/23},${27-(v-lo)/(hi-lo||1)*24}`).join(" ")}" fill="none" stroke="#8fb898" stroke-width="2"/>`;
  $("exportBar").hidden=false;
}
function renderTimeline() {
  if(!state.result) return;
  $("timeline").innerHTML=state.result.rows.map((r,i)=>`<button class="hour-slot ${r.grid_mode==="renewable_storage"?"storage":""} ${r.critical_overload?"critical":""} ${i===state.selected?"active":""}" data-index="${i}" aria-pressed="${i===state.selected}" aria-label="${hour(r.timestamp)}: ${escapeHTML(r.grid_label)}, ${num(r.target_demand_kw)} kW${r.critical_overload?', critical overload':''}"><span></span>${r.timestamp.slice(11,13)}</button>`).join("");
}
$("timeline").addEventListener("click",event=>{
  const button=event.target.closest("[data-index]");if(!button) return;
  stopPlayback();state.selected=Number(button.dataset.index);renderSelected();renderTimeline();
});
function renderSelected() {
  if(!state.result) return;
  const r=state.result.rows[state.selected];
  $("socValue").textContent=num(r.soc_end_pct,0)+"%";
  $("socRing").style.setProperty("--soc",r.soc_end_pct);
  $("socRing").style.setProperty("--ring",r.battery_shortfall?"#c98962":"#75a785");
  $("batteryHour").textContent=`After ${hour(r.timestamp)} interval`;
  $("batteryCapacity").textContent=`${num(state.result.battery_settings.capacity_kwh,0)} kWh capacity`;
  $("batteryFoot").textContent=r.battery_shortfall?`${num(r.unserved_energy_kwh)} kWh shortfall this hour`:`Reserve protected at ${num(state.result.battery_settings.reserve_soc_pct,0)}% SOC`;
  $("batteryChart").innerHTML=state.result.rows.map((v,i)=>`<div class="soc-bar ${i===state.selected?'selected':''}" style="height:${Math.max(2,v.soc_end_pct)}%" title="${hour(v.timestamp)}: ${num(v.soc_end_pct)}% SOC"></div>`).join("");
  $("selectedSignal").innerHTML=`<span class="signal-icon">ϟ</span><div><strong>${hour(r.timestamp)} &nbsp;·&nbsp; ${escapeHTML(r.grid_label)} &nbsp;·&nbsp; ${num(r.target_demand_kw,2)} kW</strong><span>${escapeHTML(r.reason)}${r.battery_shortfall?' · simulated storage shortfall':''}</span></div>${r.critical_overload?'<span class="tag alert">Critical overload</span>':'<span class="tag storage">Rule evaluated</span>'}`;
  renderDemandChart();
}
function renderDemandChart() {
  const rows=state.result.rows,width=720,height=232,left=39,right=18,top=16,bottom=32;
  const max=Math.max(240,Math.ceil(Math.max(...rows.map(r=>r.target_demand_kw))/40)*40),plotW=width-left-right,plotH=height-top-bottom;
  const x=i=>left+i*plotW/23,y=v=>top+plotH-(v/max)*plotH;
  const path=rows.map((r,i)=>`${i?'L':'M'}${x(i).toFixed(2)},${y(r.target_demand_kw).toFixed(2)}`).join(" ");
  let svg=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="24-hour predicted energy demand in kilowatts. Dashed thresholds at 160 and 200 kilowatts."><defs><linearGradient id="areaFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#76af91" stop-opacity="0.20"/><stop offset="100%" stop-color="#76af91" stop-opacity="0.02"/></linearGradient></defs>`;
  rows.forEach((r,i)=>{if(Number(r.timestamp.slice(11,13))>=18&&Number(r.timestamp.slice(11,13))<=22){const start=Math.max(left,x(i)-plotW/46),end=Math.min(width-right,x(i)+plotW/46);svg+=`<rect x="${start}" y="${top}" width="${end-start}" height="${plotH}" fill="#edf4e9"/>`;}});
  const step=max>400?100:40;
  for(let v=0;v<=max;v+=step) svg+=`<line x1="${left}" y1="${y(v)}" x2="${width-right}" y2="${y(v)}" stroke="#edf1ef"/><text x="${left-10}" y="${y(v)+3}" font-size="9" fill="#97a6a3" text-anchor="end">${v}</text>`;
  for(const [threshold,color] of [[160,"#a2b5ae"],[200,"#d59d85"]]) svg+=`<line x1="${left}" y1="${y(threshold)}" x2="${width-right}" y2="${y(threshold)}" stroke="${color}" stroke-dasharray="4 4"/><text x="${width-right-2}" y="${y(threshold)-5}" fill="${color}" font-size="8" text-anchor="end">${threshold} kW</text>`;
  svg+=`<path d="${path} L${x(23)},${y(0)} L${x(0)},${y(0)} Z" fill="url(#areaFill)"/><path d="${path}" fill="none" stroke="#4b917a" stroke-width="2.5" stroke-linejoin="round"/>`;
  const selected=rows[state.selected];
  svg+=`<line x1="${x(state.selected)}" x2="${x(state.selected)}" y1="${top}" y2="${y(0)}" stroke="#63917a" stroke-width="1" stroke-dasharray="3 3" opacity=".5"/>`;
  rows.forEach((r,i)=>{
    svg+=`<circle class="forecast-point" data-index="${i}" tabindex="0" role="button" aria-label="Inspect ${hour(r.timestamp)}, ${num(r.target_demand_kw,2)} kW" cx="${x(i)}" cy="${y(r.target_demand_kw)}" r="${i===state.selected?4.5:2.7}" fill="${r.critical_overload?'#c98160':'#4b917a'}" stroke="white" stroke-width="1.5"><title>${hour(r.timestamp)} · ${num(r.target_demand_kw,2)} kW</title></circle>`;
    if(i%3===0||i===23)svg+=`<text x="${x(i)}" y="${height-9}" text-anchor="middle" font-size="9" fill="#97a6a3">${hour(r.timestamp)}</text>`;
  });
  $("demandChart").innerHTML=svg+"</svg>";
}
function chartSelect(event) {
  if(event.type==="keydown"&&!['Enter',' '].includes(event.key))return;
  const point=event.target.closest("[data-index]");if(!point)return;
  event.preventDefault();stopPlayback();state.selected=Number(point.dataset.index);renderSelected();renderTimeline();
}
$("demandChart").addEventListener("click",chartSelect);
$("demandChart").addEventListener("keydown",chartSelect);
$("playButton").addEventListener("click",()=>{
  if(!state.result)return;
  if(state.timer){stopPlayback();return;}
  $("playButton").textContent="Ⅱ  Pause simulation";
  state.timer=setInterval(()=>{state.selected=(state.selected+1)%24;renderSelected();renderTimeline();},1100);
});
function renderModel(data) {
  $("providerDetails").textContent=data.message;
  const m=data.local_validation,entries=[['Active provider',data.backend==='local'?'Local CPU model':'Zoho QuickML'],['Configuration',data.configured?'Configured':'Setup required']];
  if(m) entries.push(['Local reference model',m.selected_model],['Local holdout RMSE',`${num(m.rmse_kw,2)} kW`],['Local holdout MAE',`${num(m.mae_kw,2)} kW`],['Local holdout R²',num(m.r2,3)],['Local validation rows',`${m.validation_rows} chronological rows`],['Training rows after refit',num(m.rows,0)]);
  if(data.backend==='quickml')entries.push(['Cloud accuracy','Measure using labelled validation data']);
  $("modelDetails").innerHTML=entries.map(([k,v])=>`<div class="detail-row"><span>${escapeHTML(k)}</span><strong>${escapeHTML(v)}</strong></div>`).join("");
}
$("runButton").addEventListener("click",runForecast);$("runTelemetryButton").addEventListener("click",runForecast);
$("uploadButton").addEventListener("click",()=>$("csvFile").click());
$("csvFile").addEventListener("change",async()=>{
  const file=$("csvFile").files[0];if(!file||state.busy)return;
  if(file.size>2_000_000){showError("CSV upload limit is 2 MB.");$("csvFile").value="";return;}
  stopPlayback();busy(true);$("errorBox").hidden=true;
  try {
    const result=await api("/api/forecast-csv",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({csv:await file.text(),battery:state.battery})});
    state.source=`Uploaded CSV: ${file.name}`;applyForecast(result);switchTab("overview");
  } catch(error){showError(error.message);}
  finally {busy(false);$("csvFile").value="";}
});
async function loadSample() {
  const data=await api("/api/demo");state.rows=data.rows;state.source="Historical sample weather";
  $("manualStart").value=state.rows[0].timestamp.replace(" ","T").slice(0,16);renderTelemetry();dirty();
}
$("resetData").addEventListener("click",()=>loadSample().catch(error=>showError(error.message)));
$("createScenario").addEventListener("click",()=>{
  const start=$("manualStart").value,temp=Number($("manualTemp").value),humidity=Number($("manualHumidity").value),solar=Number($("manualSolar").value);
  if(!start||!["manualStart","manualTemp","manualHumidity","manualSolar"].every(id=>$(id).value!==""&&$(id).checkValidity())){showError("Fill the manual scenario fields within their shown ranges.");return;}
  if(start.slice(14,16)!=="00"){showError("Choose a starting hour with minutes set to 00.");return;}
  // UTC arithmetic only: timestamps remain naive local-grid strings with no conversion.
  const date=new Date(start+":00Z");if(!Number.isFinite(date.getTime())){showError("Choose a valid starting hour.");return;}
  state.rows=Array.from({length:24},(_,i)=>{
    const d=new Date(date.getTime()+i*3600000),h=d.getUTCHours();
    return {timestamp:d.toISOString().slice(0,19).replace("T"," "),ambient_temp_c:temp,humidity_pct:humidity,solar_irradiance_wm2:Number((solar*Math.max(0,Math.sin(Math.PI*(h-6)/12))).toFixed(2))};
  });state.source="Manual weather scenario";renderTelemetry();dirty();
});
$("batterySettingsButton").addEventListener("click",()=>$("batteryDialog").showModal());
$("closeBattery").addEventListener("click",()=>$("batteryDialog").close());
$("batteryForm").addEventListener("submit",event=>{
  event.preventDefault();const values=Object.fromEntries([...new FormData(event.target)].map(([k,v])=>[k,Number(v)]));
  if(values.reserve_soc_pct>values.initial_soc_pct){$("batteryDialog").close();showError("Reserve SOC must not exceed initial SOC.");return;}
  state.battery=values;$("batteryDialog").close();dirty();runForecast();
});
$("exportButton").addEventListener("click",()=>{
  if(!state.result)return;
  const columns=['timestamp','target_demand_kw','grid_mode','critical_overload','soc_start_pct','soc_end_pct','solar_estimate_kw','unserved_energy_kwh','battery_shortfall'];
  const csv=[columns.join(','),...state.result.rows.map(row=>columns.map(c=>typeof row[c]==='number'?row[c].toFixed(6):String(row[c])).join(','))].join('\r\n');
  const url=URL.createObjectURL(new Blob([csv],{type:'text/csv;charset=utf-8'}));
  const link=document.createElement('a');link.href=url;link.download='gridpulse_dispatch.csv';document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
});
async function init() {
  try {
    const status=await api("/api/status");renderModel(status);
    $("providerBadge").textContent=status.backend==='local'?'●  Local model · demo':(status.configured?'○  QuickML · configured':'○  QuickML · setup needed');
    await loadSample();
    if(status.configured)await runForecast();else showError(status.message+". See README.md for setup steps.");
  }catch(error){showError(error.message);$("providerBadge").textContent='Setup required';}
}
init();
