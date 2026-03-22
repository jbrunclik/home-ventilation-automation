// Shelly 2PM Fan Controller (cover mode)
//
// Standalone script running on the Shelly — no external server required.
// Mirrors the Python daemon's architecture: cached state → pure decision
// logic → actuation. Adding new inputs (CO2, humidity) means:
//   1. Add a poller that updates cached state
//   2. Add a rule in desiredSpeed()
//   3. Call evaluate() after updating state
//
// Fan speed via cover mode:
//   OFF  → Cover.Stop  (both relays off)
//   LOW  → Cover.Open  (relay 0)
//   HIGH → Cover.Close (relay 1)
//
// Decision priority (highest → lowest):
//   1. Manual switch override → HIGH for OVERRIDE_MINUTES
//   2. (Future: humidity)
//   3. (Future: CO2)
//   4. Time-based schedule → LOW
//   5. Off
//
// Setup: Shelly web UI → Scripts → add this script, enable "Run on startup".
//        Set both inputs to type "switch" if using wall toggle switches.

// --- Configuration ---
let OVERRIDE_MINUTES = 10;
let REFRESH_SECONDS = 60;   // re-issue cover command to prevent 300s auto-stop
let INPUT_ID = 0;           // which input triggers the override (0 or 1)

// Schedule: run LOW for first RUN_MINUTES of each hour within the time window
let SCHEDULE_START_HOUR = 8;
let SCHEDULE_END_HOUR = 18;
let SCHEDULE_RUN_MINUTES = 10;
let SCHEDULE_DAYS = [1, 2, 3, 4, 5]; // 0=Sun .. 6=Sat

// --- Cached state (updated by pollers/events, read by desiredSpeed) ---
let overrideActive = false;
let scheduleActive = false;
// Future: let co2Ppm = 0;
// Future: let humidityPct = 0;

// --- Actuation state ---
let currentSpeed = null; // "off", "low", "high", null = unknown
let overrideTimer = null;
let refreshTimer = null;

// Detach inputs so only this script controls the cover.
// in_locked is set separately — firmware ignores it when sent with in_mode.
Shelly.call("Cover.SetConfig", {
  id: 0,
  config: { maxtime_open: 300, maxtime_close: 300, in_mode: "detached" },
});
Shelly.call("Cover.SetConfig", { id: 0, config: { in_locked: true } });

// ---------------------------------------------------------------------------
// Decision logic (pure — no I/O, no side effects)
// ---------------------------------------------------------------------------

function desiredSpeed() {
  if (overrideActive) return "high";
  // Future: if (humidityPct > 70) return "high";
  // Future: if (humidityPct > 60) return "low";
  // Future: if (co2Ppm > 1200) return "high";
  // Future: if (co2Ppm > 800) return "low";
  if (scheduleActive) return "low";
  return "off";
}

// ---------------------------------------------------------------------------
// Actuation — applies desired speed, skips if already there
// ---------------------------------------------------------------------------

let SPEED_CMD = { off: "Cover.Stop", low: "Cover.Open", high: "Cover.Close" };

function applySpeed(speed) {
  if (speed === currentSpeed) return;
  currentSpeed = speed;

  // Clear old refresh
  if (refreshTimer) {
    Timer.clear(refreshTimer);
    refreshTimer = null;
  }

  let cmd = SPEED_CMD[speed];
  Shelly.call(cmd, { id: 0 });

  // Keep the cover moving (it auto-stops after 300s)
  if (speed !== "off") {
    refreshTimer = Timer.set(REFRESH_SECONDS * 1000, true, function () {
      Shelly.call(cmd, { id: 0 });
    });
  }
}

// Central evaluation — call after any state change
function evaluate() {
  applySpeed(desiredSpeed());
}

// ---------------------------------------------------------------------------
// Switch override
// ---------------------------------------------------------------------------

function startOverride() {
  overrideActive = true;
  if (overrideTimer) Timer.clear(overrideTimer);
  overrideTimer = Timer.set(OVERRIDE_MINUTES * 60 * 1000, false, function () {
    overrideTimer = null;
    overrideActive = false;
    evaluate(); // seamlessly transitions to schedule/off
  });
  evaluate();
}

Shelly.addEventHandler(function (ev) {
  if (
    ev.component === "input:" + JSON.stringify(INPUT_ID) &&
    ev.info.event === "toggle"
  ) {
    startOverride();
  }
});

// ---------------------------------------------------------------------------
// Schedule poller — updates scheduleActive, then re-evaluates
// ---------------------------------------------------------------------------

function updateSchedule() {
  if (overrideActive) return; // no point checking, override wins

  Shelly.call("Sys.GetStatus", {}, function (res) {
    if (!res || !res.unixtime || !res.time) return;

    var hour = parseInt(res.time.slice(0, 2), 10);
    var minute = parseInt(res.time.slice(3, 5), 10);

    // Derive local weekday from UTC offset
    var utcHour = Math.floor((res.unixtime % 86400) / 3600);
    var offsetHours = hour - utcHour;
    if (offsetHours > 12) offsetHours -= 24;
    if (offsetHours < -12) offsetHours += 24;
    var localUnix = res.unixtime + offsetHours * 3600;
    var day = (Math.floor(localUnix / 86400) + 4) % 7;

    var dayMatch = false;
    for (var i = 0; i < SCHEDULE_DAYS.length; i++) {
      if (SCHEDULE_DAYS[i] === day) { dayMatch = true; break; }
    }

    var inWindow = dayMatch && hour >= SCHEDULE_START_HOUR && hour < SCHEDULE_END_HOUR;
    scheduleActive = inWindow && minute < SCHEDULE_RUN_MINUTES;
    evaluate();
  });
}

Timer.set(30 * 1000, true, function () { updateSchedule(); });
updateSchedule(); // check on startup
