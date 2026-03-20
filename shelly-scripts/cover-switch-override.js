// Cover Switch Override + Schedule for Shelly 2PM Gen2+
//
// Standalone script that runs on the Shelly device itself — no external
// server required.
//
// Features:
//   1. Switch override: toggle → fan runs HIGH for OVERRIDE_MINUTES, then stops
//   2. Time-based schedule: run LOW for first RUN_MINUTES of each hour during
//      configured window (hours + weekdays), unless overridden
//   3. Handles 300s cover auto-stop by re-issuing the command every 60s
//
// Priority: switch override (HIGH) > schedule (LOW) > off
//
// Setup: Shelly web UI → Scripts → add this script, enable "Run on startup".

// --- Configuration ---
let OVERRIDE_MINUTES = 10;  // how long to keep the fan on after switch press
let REFRESH_SECONDS = 60;   // re-issue cover command to prevent 300s auto-stop
let INPUT_ID = 0;           // which input to listen to (0 or 1)

// Schedule: run LOW for first RUN_MINUTES of each hour within the time window
// Uses the device's configured timezone (Settings → Location) for local time,
// so DST is handled automatically — no manual offset needed.
let SCHEDULE_START_HOUR = 8;   // schedule active from 08:00...
let SCHEDULE_END_HOUR = 18;    // ...until 18:00 (exclusive)
let SCHEDULE_RUN_MINUTES = 10; // run first 10 minutes of each hour
let SCHEDULE_DAYS = [1, 2, 3, 4, 5]; // 0=Sun, 1=Mon, ..., 6=Sat

// --- State ---
let mode = "idle";  // "idle", "override", "schedule"
let overrideTimer = null;
let refreshTimer = null;

// Set cover timeouts to maximum (300s) and lock inputs on startup.
// Locking prevents the default cover behavior from interfering — the script
// handles switch events itself via addEventHandler.
Shelly.call("Cover.SetConfig", {
  id: 0,
  config: { maxtime_open: 300, maxtime_close: 300, in_locked: true },
});

function startRefresh(method) {
  if (refreshTimer) Timer.clear(refreshTimer);
  refreshTimer = Timer.set(REFRESH_SECONDS * 1000, true, function () {
    Shelly.call(method, { id: 0 });
  });
}

function stopFan() {
  if (refreshTimer) {
    Timer.clear(refreshTimer);
    refreshTimer = null;
  }
  if (overrideTimer) {
    Timer.clear(overrideTimer);
    overrideTimer = null;
  }
  mode = "idle";
  Shelly.call("Cover.Stop", { id: 0 });
}

function startOverride() {
  mode = "override";
  Shelly.call("Cover.Close", { id: 0 }); // HIGH
  startRefresh("Cover.Close");

  if (overrideTimer) Timer.clear(overrideTimer);
  overrideTimer = Timer.set(OVERRIDE_MINUTES * 60 * 1000, false, function () {
    overrideTimer = null;
    // Fall back to schedule check instead of stopping blindly
    checkSchedule();
  });
}

function checkSchedule() {
  // Don't interrupt an active override
  if (mode === "override") return;

  Shelly.call("Sys.GetStatus", {}, function (res) {
    if (!res || !res.unixtime || !res.time) return;

    // Parse local time from device (DST-aware via configured timezone)
    var hour = parseInt(res.time.slice(0, 2), 10);
    var minute = parseInt(res.time.slice(3, 5), 10);

    // Derive UTC offset from local time vs unixtime to get local weekday
    var utcHour = Math.floor((res.unixtime % 86400) / 3600);
    var offsetHours = hour - utcHour;
    if (offsetHours > 12) offsetHours -= 24;
    if (offsetHours < -12) offsetHours += 24;
    var localUnix = res.unixtime + offsetHours * 3600;
    // Jan 1 1970 was Thursday (4). 0=Sun, 1=Mon, ..., 6=Sat
    var day = (Math.floor(localUnix / 86400) + 4) % 7;

    var dayMatch = false;
    for (var i = 0; i < SCHEDULE_DAYS.length; i++) {
      if (SCHEDULE_DAYS[i] === day) {
        dayMatch = true;
        break;
      }
    }

    var inWindow = dayMatch && hour >= SCHEDULE_START_HOUR && hour < SCHEDULE_END_HOUR;
    var shouldRun = inWindow && minute < SCHEDULE_RUN_MINUTES;

    if (shouldRun && mode !== "schedule") {
      mode = "schedule";
      Shelly.call("Cover.Open", { id: 0 }); // LOW
      startRefresh("Cover.Open");
    } else if (!shouldRun && mode === "schedule") {
      stopFan();
    }
  });
}

// Check schedule every 30s
Timer.set(30 * 1000, true, function () {
  checkSchedule();
});

// Also check immediately on startup
checkSchedule();

// Switch override
Shelly.addEventHandler(function (ev) {
  if (ev.component === "input:" + JSON.stringify(INPUT_ID) && ev.info.event === "toggle") {
    startOverride();
  }
});
