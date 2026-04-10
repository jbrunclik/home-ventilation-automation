#include "webhook_server.h"

#include <ArduinoJson.h>
#include <WebServer.h>
#include <WiFi.h>

static WebServer* server = nullptr;
static WebhookState* g_state = nullptr;
static const FanState* g_fan_state = nullptr;
static const TuyaReading* g_reading = nullptr;
static const History* g_history = nullptr;
static const Config* g_config = nullptr;

// clang-format off
static const char HTML_PAGE[] PROGMEM = R"rawhtml(<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ventilation</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#1e1e2e;color:#cdd6f4;font-family:sans-serif;min-height:100vh}
.content{padding:16px;max-width:480px;margin:0 auto}
.card{background:#181825;border-radius:12px;padding:16px;margin-bottom:14px}
.card h2{font-size:.75rem;color:#585b70;text-transform:uppercase;letter-spacing:.07em;margin-bottom:14px}
.co2{font-size:3.2rem;font-weight:700;text-align:center;line-height:1}
.co2-unit{text-align:center;color:#45475a;font-size:.8rem;margin:.4rem 0 1rem}
.g{color:#a6e3a1}.y{color:#f9e2af}.r{color:#f38ba8}.x{color:#585b70}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}
.tile{background:#313244;border-radius:8px;padding:10px 12px}
.tile-val{font-size:1.2rem;font-weight:600}
.tile-lbl{font-size:.68rem;color:#585b70;margin-top:3px}
.fan{text-align:center;padding:13px;border-radius:8px;font-size:.95rem;font-weight:700;letter-spacing:.05em;margin-bottom:6px}
.fan-off{background:#313244;color:#585b70}
.fan-low{background:#89b4fa18;color:#89b4fa}
.fan-high{background:#f38ba818;color:#f38ba8}
.cooldown{text-align:center;color:#f9e2af;font-size:.88rem;min-height:1.4em}
.btn{padding:15px;border:none;border-radius:10px;font-size:1rem;font-weight:600;cursor:pointer;width:100%;transition:filter .1s}
.btn:active{filter:brightness(.7)}
.btn-on{background:#2b5a2e;color:#a6e3a1}
.btn-off{background:#5a2035;color:#f38ba8}
.btn:disabled{opacity:.35;cursor:not-allowed;filter:none}
.sw-warn{text-align:center;color:#f9e2af;font-size:.85rem;margin-bottom:10px}
.mtabs{display:flex;gap:6px;margin-bottom:12px;flex-wrap:wrap}
.mtab{padding:6px 12px;border:1px solid #313244;border-radius:6px;background:none;color:#6c7086;font-size:.8rem;cursor:pointer;transition:.15s}
.mtab.active{background:#89b4fa22;border-color:#89b4fa;color:#89b4fa}
canvas{display:block;width:100%;border-radius:8px}
.stats{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-top:12px}
.stat{background:#313244;border-radius:8px;padding:8px;text-align:center}
.stat-val{font-size:1rem;font-weight:600}
.stat-lbl{font-size:.65rem;color:#585b70;margin-top:2px}
.sbar{display:flex;justify-content:space-between;font-size:.7rem;color:#45475a;margin-top:12px}
.err{background:#302030;border:1px solid #7b3050;border-radius:8px;padding:10px;color:#f38ba8;text-align:center;margin-bottom:12px;display:none;font-size:.88rem}
.hint{color:#585b70;font-size:.8rem;text-align:center;padding:20px 0}
</style>
</head>
<body>
<div class="content">
  <div id="err" class="err">Cannot reach device</div>
  <div class="card">
    <h2>Air Quality</h2>
    <div id="co2" class="co2 x">---</div>
    <div class="co2-unit">ppm CO&#8322;</div>
    <div class="grid">
      <div class="tile"><div id="temp" class="tile-val">---</div><div class="tile-lbl">Temperature (&#176;C)</div></div>
      <div class="tile"><div id="hum" class="tile-val">---</div><div class="tile-lbl">Humidity (%)</div></div>
      <div class="tile"><div id="pm25" class="tile-val">---</div><div class="tile-lbl">PM2.5 (&#181;g/m&#179;)</div></div>
      <div class="tile"><div id="rssi" class="tile-val">---</div><div class="tile-lbl">WiFi (dBm)</div></div>
    </div>
  </div>
  <div class="card">
    <h2>Fan</h2>
    <div id="fan" class="fan fan-off">OFF</div>
    <div id="cd" class="cooldown"></div>
    <div id="sw-warn" class="sw-warn" style="display:none">Wall switch active &#8212; manual control disabled</div>
    <button class="btn btn-on" id="ctrl-btn" onclick="toggle()">Turn On</button>
    <div class="sbar"><span id="up">--</span><span id="ts">---</span></div>
  </div>
  <div class="card">
    <h2>Long-term trends <span style="font-weight:400;color:#45475a;text-transform:none;letter-spacing:0">&#8212; last 12 h</span></h2>
    <div class="mtabs">
      <button class="mtab active" onclick="selMetric('co2',this)">CO&#8322;</button>
      <button class="mtab" onclick="selMetric('temp',this)">Temp</button>
      <button class="mtab" onclick="selMetric('hum',this)">Humidity</button>
      <button class="mtab" onclick="selMetric('pm25',this)">PM2.5</button>
    </div>
    <canvas id="chart" height="160"></canvas>
    <div class="stats">
      <div class="stat"><div id="s-cur" class="stat-val">--</div><div class="stat-lbl">Current</div></div>
      <div class="stat"><div id="s-min" class="stat-val">--</div><div class="stat-lbl">Min</div></div>
      <div class="stat"><div id="s-avg" class="stat-val">--</div><div class="stat-lbl">Avg</div></div>
      <div class="stat"><div id="s-max" class="stat-val">--</div><div class="stat-lbl">Max</div></div>
    </div>
  </div>
  <div class="card">
    <h2>Fan activity</h2>
    <canvas id="fan-chart" height="36"></canvas>
  </div>
  <div id="hist-hint" class="hint" style="display:none">Collecting data &#8212; samples every 5 min</div>
</div>
<script>
let ok=false;
async function poll(){
  try{
    const r=await fetch('/status',{signal:AbortSignal.timeout(3000)});
    if(!r.ok)throw 0;
    const d=await r.json();
    document.getElementById('err').style.display='none';ok=true;
    const co2El=document.getElementById('co2');
    if(d.co2_ppm!=null){co2El.textContent=d.co2_ppm;co2El.className='co2 '+(d.co2_ppm<800?'g':d.co2_ppm<=1200?'y':'r');}
    else{co2El.textContent='---';co2El.className='co2 x';}
    document.getElementById('temp').textContent=d.temperature!=null?d.temperature.toFixed(1)+'\u00b0':'---';
    document.getElementById('hum').textContent=d.humidity!=null?d.humidity.toFixed(0)+'%':'---';
    document.getElementById('pm25').textContent=d.pm25!=null?d.pm25.toFixed(1):'---';
    document.getElementById('rssi').textContent=d.wifi_rssi!=null?d.wifi_rssi:'---';
    const sp=d.fan_speed||'off';
    const fan=document.getElementById('fan');
    fan.className='fan '+(sp==='high'?'fan-high':sp==='low'?'fan-low':'fan-off');
    fan.textContent=sp==='high'?'HIGH':sp==='low'?'LOW':'OFF';
    const cd=document.getElementById('cd');
    if(d.override_remaining_seconds>0){const s=d.override_remaining_seconds;cd.textContent='Cooldown: '+Math.floor(s/60)+':'+String(s%60).padStart(2,'0');}
    else cd.textContent='';
    inCooldown=d.override_remaining_seconds>0;
    const btn=document.getElementById('ctrl-btn');
    btn.textContent=inCooldown?'Cancel Cooldown':'Turn On';
    btn.className='btn '+(inCooldown?'btn-off':'btn-on');
    const sw=!!d.switch_active;
    document.getElementById('sw-warn').style.display=sw?'block':'none';
    btn.disabled=sw;
    if(d.uptime_seconds!=null){const u=d.uptime_seconds;document.getElementById('up').textContent=u<3600?'Up '+Math.floor(u/60)+'m':'Up '+Math.floor(u/3600)+'h '+Math.floor(u%3600/60)+'m';}
    document.getElementById('ts').textContent=new Date().toLocaleTimeString();
  }catch(e){if(ok){document.getElementById('err').style.display='block';ok=false;}}
}
let inCooldown=false;
async function toggle(){
  const action=inCooldown?'cancel':'on';
  try{await fetch('/api/control?action='+action,{method:'POST',signal:AbortSignal.timeout(3000)});setTimeout(poll,300);}
  catch(e){document.getElementById('err').style.display='block';}
}
const METRICS={co2:{key:'co2',color:'#89b4fa'},temp:{key:'temp',color:'#fab387'},hum:{key:'hum',color:'#89dceb'},pm25:{key:'pm25',color:'#cba6f7'}};
let activeMetric='co2',histData=[];
function selMetric(k,el){activeMetric=k;document.querySelectorAll('.mtab').forEach(t=>t.classList.remove('active'));el.classList.add('active');renderCharts();}
async function refreshHistory(){
  try{
    const r=await fetch('/api/history',{signal:AbortSignal.timeout(5000)});
    if(!r.ok)return;
    const d=await r.json();
    histData=d.entries||[];
    document.getElementById('hist-hint').style.display=histData.length<2?'block':'none';
    renderCharts();
  }catch(e){}
}
function renderCharts(){
  const m=METRICS[activeMetric];
  const vals=histData.map(e=>e[m.key]).filter(v=>v!=null&&v>=0);
  if(vals.length){
    const mn=Math.min(...vals),mx=Math.max(...vals),avg=vals.reduce((a,b)=>a+b,0)/vals.length;
    document.getElementById('s-cur').textContent=vals[vals.length-1].toFixed(1);
    document.getElementById('s-min').textContent=mn.toFixed(1);
    document.getElementById('s-avg').textContent=avg.toFixed(1);
    document.getElementById('s-max').textContent=mx.toFixed(1);
  }else['s-cur','s-min','s-avg','s-max'].forEach(id=>document.getElementById(id).textContent='--');
  drawLineChart(document.getElementById('chart'),histData,m);
  drawFanChart(document.getElementById('fan-chart'),histData);
}
function drawLineChart(canvas,data,m){
  const W=canvas.offsetWidth||320,H=160;
  canvas.width=W;canvas.height=H;
  const ctx=canvas.getContext('2d');
  const PL=38,PR=8,PT=8,PB=22,IW=W-PL-PR,IH=H-PT-PB;
  ctx.fillStyle='#11111b';ctx.fillRect(0,0,W,H);
  const vals=data.map(e=>e[m.key]).filter(v=>v!=null&&v>=0);
  if(vals.length<2){
    ctx.fillStyle='#45475a';ctx.font='12px sans-serif';ctx.textAlign='center';
    ctx.fillText(vals.length===1?'1 sample \u2014 need more':'No data yet',W/2,H/2);return;
  }
  let mn=Math.min(...vals),mx=Math.max(...vals);
  const pad=(mx-mn)*0.08||1;mn-=pad;mx+=pad;const rng=mx-mn;
  const tx=i=>PL+(i/(data.length-1))*IW;
  const ty=v=>PT+(1-(v-mn)/rng)*IH;
  ctx.strokeStyle='#313244';ctx.lineWidth=1;
  ctx.fillStyle='#585b70';ctx.font='9px sans-serif';ctx.textAlign='right';
  for(let g=0;g<=4;g++){
    const y=PT+(g/4)*IH;
    ctx.beginPath();ctx.moveTo(PL,y);ctx.lineTo(W-PR,y);ctx.stroke();
    ctx.fillText((mx-(g/4)*rng).toFixed(0),PL-3,y+3);
  }
  const grad=ctx.createLinearGradient(0,PT,0,PT+IH);
  grad.addColorStop(0,m.color+'55');grad.addColorStop(1,m.color+'08');
  ctx.fillStyle=grad;ctx.beginPath();ctx.moveTo(tx(0),PT+IH);
  data.forEach((e,i)=>{const v=e[m.key];if(v!=null&&v>=0)ctx.lineTo(tx(i),ty(v));});
  ctx.lineTo(tx(data.length-1),PT+IH);ctx.closePath();ctx.fill();
  ctx.strokeStyle=m.color;ctx.lineWidth=1.5;ctx.lineJoin='round';ctx.beginPath();
  let first=true;
  data.forEach((e,i)=>{const v=e[m.key];if(v==null||v<0){first=true;return;}first?ctx.moveTo(tx(i),ty(v)):ctx.lineTo(tx(i),ty(v));first=false;});
  ctx.stroke();
  ctx.fillStyle='#585b70';ctx.font='9px sans-serif';
  const lastT=data[data.length-1]?.t||0;
  [0,0.5,1].forEach(f=>{
    const i=Math.round(f*(data.length-1));
    const dt=lastT-data[i].t;
    const lbl=dt<60?'now':dt<3600?'-'+Math.round(dt/60)+'m':'-'+Math.round(dt/3600*10)/10+'h';
    ctx.textAlign=f===0?'left':f===1?'right':'center';
    ctx.fillText(lbl,tx(i),H-5);
  });
}
function drawFanChart(canvas,data){
  const W=canvas.offsetWidth||320,H=36;
  canvas.width=W;canvas.height=H;
  const ctx=canvas.getContext('2d');
  ctx.fillStyle='#11111b';ctx.fillRect(0,0,W,H);
  if(!data.length)return;
  const bw=W/data.length;
  data.forEach((e,i)=>{if(e.fan===2){ctx.fillStyle='#f38ba855';ctx.fillRect(i*bw,4,Math.max(bw,1),H-8);}else if(e.fan===1){ctx.fillStyle='#89b4fa55';ctx.fillRect(i*bw,4,Math.max(bw,1),H-8);}});
  ctx.fillStyle='#585b70';ctx.font='9px sans-serif';ctx.textAlign='left';ctx.fillText('low',4,H-6);
  ctx.fillStyle='#585b70';ctx.textAlign='right';ctx.fillText('high',W-4,H-6);
}
poll();setInterval(poll,2000);
refreshHistory();setInterval(refreshHistory,60000);
</script>
</body>
</html>)rawhtml";
// clang-format on

static void handleRoot() {
    server->send_P(200, "text/html", HTML_PAGE);
}

static void handleControl() {
    if (!server->hasArg("action")) {
        server->send(400, "text/plain", "Missing action");
        return;
    }
    String action = server->arg("action");
    if (action == "on") {
        g_state->pending_action = PendingAction::OFF_COOLDOWN;
    } else if (action == "cancel") {
        g_state->pending_action = PendingAction::OFF_IMMEDIATE;
    } else {
        server->send(400, "text/plain", "Unknown action");
        return;
    }
    g_state->reevaluate = true;
    Serial.printf("Control: action=%s\n", action.c_str());
    server->send(200, "text/plain", "OK");
}

static void handleWebhook() {
    // Switch event: ?input_id=N&state=on|off
    if (server->hasArg("input_id") && server->hasArg("state")) {
        int input_id = server->arg("input_id").toInt();
        bool on = server->arg("state").equalsIgnoreCase("on");

        if (input_id >= 0 && input_id < MAX_SWITCH_INPUTS) {
            g_state->switch_states[input_id] = on;
            g_state->reevaluate = true;
            Serial.printf("Webhook: switch input %d → %s\n", input_id, on ? "ON" : "OFF");
        }
        server->send(200, "text/plain", "OK");
        return;
    }

    // Unknown params
    Serial.printf("Webhook: unrecognized params: %s\n", server->uri().c_str());
    server->send(200, "text/plain", "OK");
}

static void handleStatus() {
    JsonDocument doc;
    doc["uptime_seconds"] = millis() / 1000;
    doc["wifi_rssi"] = WiFi.RSSI();
    doc["fan_speed"] = fanSpeedStr(g_fan_state->current_speed);

    if (g_fan_state->override_until_ms != 0) {
        long remaining = (long)(g_fan_state->override_until_ms - millis());
        doc["override_remaining_seconds"] = remaining > 0 ? remaining / 1000 : 0;
    }

    if (g_reading->valid) {
        doc["co2_ppm"] = g_reading->co2;
        if (g_reading->temperature >= 0) doc["temperature"] = g_reading->temperature;
        if (g_reading->humidity >= 0) doc["humidity"] = g_reading->humidity;
        if (g_reading->pm25 >= 0) doc["pm25"] = g_reading->pm25;
    }

    bool sw_active = false;
    for (int i = 0; i < g_config->switch_input_count; i++) {
        if (g_state->switch_states[i]) { sw_active = true; break; }
    }
    doc["switch_active"] = sw_active;

    String json;
    serializeJsonPretty(doc, json);
    server->send(200, "application/json", json);
}


static void handleHistory() {
    // Build JSON manually to avoid large ArduinoJson allocation
    String json;
    json.reserve(g_history->size() * 68 + 64);
    json += "{\"interval_s\":";
    json += HISTORY_INTERVAL_S;
    json += ",\"count\":";
    json += g_history->size();
    json += ",\"entries\":[";
    for (int i = 0; i < g_history->size(); i++) {
        const HistoryEntry& e = g_history->get(i);
        if (i > 0) json += ',';
        json += "{\"t\":";
        json += e.uptime_s;
        if (e.co2 >= 0) { json += ",\"co2\":"; json += e.co2; }
        if (e.temperature >= 0) { json += ",\"temp\":"; json += e.temperature; }
        if (e.humidity >= 0) { json += ",\"hum\":"; json += e.humidity; }
        if (e.pm25 >= 0) { json += ",\"pm25\":"; json += e.pm25; }
        json += ",\"fan\":";
        json += String(e.fan_speed);
        json += '}';
    }
    json += "]}";
    server->send(200, "application/json", json);
}

void webhookServerSetup(int port, WebhookState* state,
                        const FanState* fan_state, const TuyaReading* reading,
                        const History* history, const Config* config) {
    g_state = state;
    g_fan_state = fan_state;
    g_reading = reading;
    g_history = history;
    g_config = config;

    server = new WebServer(port);
    server->on("/", handleRoot);
    server->on("/api/control", HTTP_POST, handleControl);
    server->on("/api/history", handleHistory);
    server->on("/webhook/shelly", handleWebhook);
    server->on("/status", handleStatus);
    server->begin();
    Serial.printf("Webhook server started on port %d\n", port);
}

void webhookServerLoop() {
    if (server) server->handleClient();
}
