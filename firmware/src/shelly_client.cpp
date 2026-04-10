#include "shelly_client.h"

#include <ArduinoJson.h>
#include <HTTPClient.h>

static constexpr int HTTP_TIMEOUT_MS = 5000;

static bool shellyGet(const char* host, const char* path, JsonDocument* doc = nullptr) {
    HTTPClient http;
    char url[128];
    snprintf(url, sizeof(url), "http://%s%s", host, path);
    http.begin(url);
    http.setTimeout(HTTP_TIMEOUT_MS);
    int code = http.GET();
    bool ok = (code >= 200 && code < 300);
    if (ok && doc) {
        deserializeJson(*doc, http.getStream());
    }
    http.end();
    return ok;
}

static bool shellyPost(const char* host, const char* path, const char* json_body,
                       JsonDocument* doc = nullptr) {
    HTTPClient http;
    char url[128];
    snprintf(url, sizeof(url), "http://%s%s", host, path);
    http.begin(url);
    http.setTimeout(HTTP_TIMEOUT_MS);
    http.addHeader("Content-Type", "application/json");
    int code = http.POST((uint8_t*)json_body, strlen(json_body));
    bool ok = (code >= 200 && code < 300);
    if (ok && doc) {
        deserializeJson(*doc, http.getStream());
    }
    http.end();
    return ok;
}

static const char* speedToRpc(FanSpeed speed) {
    switch (speed) {
        case FanSpeed::SPEED_LOW: return "/rpc/Cover.Open?id=0";
        case FanSpeed::SPEED_HIGH: return "/rpc/Cover.Close?id=0";
        default: return "/rpc/Cover.Stop?id=0";
    }
}

bool shellySetFanSpeed(const char* host, FanSpeed speed) {
    // Stop first — cover can't switch directly between Open and Close
    if (!shellyGet(host, "/rpc/Cover.Stop?id=0")) {
        Serial.printf("Shelly: failed to stop cover on %s\n", host);
        return false;
    }

    if (speed != FanSpeed::SPEED_OFF) {
        delay(500);  // Brief delay for firmware to complete stop transition
        if (!shellyGet(host, speedToRpc(speed))) {
            Serial.printf("Shelly: failed to set %s on %s\n", fanSpeedStr(speed), host);
            return false;
        }
    }

    Serial.printf("Shelly: set fan speed to %s on %s\n", fanSpeedStr(speed), host);
    return true;
}

bool shellyRefreshFanSpeed(const char* host, FanSpeed speed) {
    if (!shellyGet(host, speedToRpc(speed))) {
        Serial.printf("Shelly: failed to refresh %s on %s\n", fanSpeedStr(speed), host);
        return false;
    }
    return true;
}

int shellyGetSwitchInputs(const char* host, bool* states, int count) {
    int read = 0;
    for (int i = 0; i < count && i < 2; i++) {
        char path[48];
        snprintf(path, sizeof(path), "/rpc/Input.GetStatus?id=%d", i);
        JsonDocument doc;
        if (shellyGet(host, path, &doc)) {
            states[i] = doc["state"] | false;
            read++;
        }
    }
    return read;
}

bool shellyConfigureCover(const char* host) {
    // Stop cover first — firmware rejects SetConfig while running
    shellyGet(host, "/rpc/Cover.Stop?id=0");

    // Set cover mode: detached, maxtime 300s
    if (!shellyPost(host, "/rpc/Cover.SetConfig",
            R"({"id":0,"config":{"maxtime_open":300,"maxtime_close":300,"in_mode":"detached"}})")) {
        Serial.printf("Shelly: failed to set cover config on %s\n", host);
        return false;
    }

    // Set in_locked separately — firmware ignores it when sent with in_mode
    if (!shellyPost(host, "/rpc/Cover.SetConfig",
            R"({"id":0,"config":{"in_locked":true}})")) {
        Serial.printf("Shelly: failed to lock cover inputs on %s\n", host);
        return false;
    }

    Serial.printf("Shelly: configured cover (detached + locked) on %s\n", host);
    return true;
}

bool shellyConfigureInputs(const char* host) {
    for (int input_id = 0; input_id < 2; input_id++) {
        char path[48];
        snprintf(path, sizeof(path), "/rpc/Input.GetConfig?id=%d", input_id);
        JsonDocument doc;
        if (!shellyGet(host, path, &doc)) continue;

        const char* type = doc["type"] | "";
        if (strcmp(type, "switch") != 0) {
            char body[64];
            snprintf(body, sizeof(body),
                     R"({"id":%d,"config":{"type":"switch"}})", input_id);
            shellyPost(host, "/rpc/Input.SetConfig", body);
            Serial.printf("Shelly: set input:%d to switch type on %s\n", input_id, host);
        }
    }
    return true;
}

bool shellyConfigureWebhooks(const char* host, const int* switch_inputs,
                             int input_count, const char* esp_ip, int port) {
    char base_url[64];
    snprintf(base_url, sizeof(base_url), "http://%s:%d/webhook/shelly", esp_ip, port);

    // Fetch current webhooks
    JsonDocument list_doc;
    if (!shellyGet(host, "/rpc/Webhook.List", &list_doc)) {
        Serial.printf("Shelly: failed to list webhooks on %s\n", host);
        return false;
    }

    JsonArray hooks = list_doc["hooks"];

    // Build desired webhook set
    struct DesiredHook {
        int cid;
        const char* event;
        const char* state;
        char url[128];
        char name[32];
        bool found;
    };

    DesiredHook desired[4];
    int desired_count = 0;

    for (int i = 0; i < input_count && desired_count < 4; i++) {
        int id = switch_inputs[i];
        // toggle_on → state=on
        snprintf(desired[desired_count].url, sizeof(desired[0].url),
                 "%s?input_id=%d&state=on", base_url, id);
        snprintf(desired[desired_count].name, sizeof(desired[0].name),
                 "Input (%d) On", id);
        desired[desired_count].cid = id;
        desired[desired_count].event = "input.toggle_on";
        desired[desired_count].state = "on";
        desired[desired_count].found = false;
        desired_count++;

        // toggle_off → state=off
        snprintf(desired[desired_count].url, sizeof(desired[0].url),
                 "%s?input_id=%d&state=off", base_url, id);
        snprintf(desired[desired_count].name, sizeof(desired[0].name),
                 "Input (%d) Off", id);
        desired[desired_count].cid = id;
        desired[desired_count].event = "input.toggle_off";
        desired[desired_count].state = "off";
        desired[desired_count].found = false;
        desired_count++;
    }

    int changes = 0;

    // Check existing hooks against desired
    for (JsonObject h : hooks) {
        int cid = h["cid"] | -1;
        const char* event = h["event"] | "";
        int hook_id = h["id"] | -1;

        bool is_desired = false;
        for (int i = 0; i < desired_count; i++) {
            if (desired[i].cid == cid && strcmp(desired[i].event, event) == 0) {
                desired[i].found = true;
                is_desired = true;

                // Check URL matches
                JsonArray urls = h["urls"];
                const char* current_url = (urls && urls.size() > 0) ? urls[0].as<const char*>() : "";
                if (strcmp(current_url, desired[i].url) != 0) {
                    char body[256];
                    snprintf(body, sizeof(body),
                             R"({"id":%d,"urls":["%s"]})", hook_id, desired[i].url);
                    shellyPost(host, "/rpc/Webhook.Update", body);
                    Serial.printf("Shelly: updated webhook %s cid=%d on %s\n", event, cid, host);
                    changes++;
                }
                break;
            }
        }

        // Delete stale hooks (not in desired set)
        if (!is_desired) {
            char body[32];
            snprintf(body, sizeof(body), R"({"id":%d})", hook_id);
            shellyPost(host, "/rpc/Webhook.Delete", body);
            Serial.printf("Shelly: deleted stale webhook %s cid=%d on %s\n", event, cid, host);
            changes++;
        }
    }

    // Create missing
    for (int i = 0; i < desired_count; i++) {
        if (!desired[i].found) {
            char body[256];
            snprintf(body, sizeof(body),
                     R"({"cid":%d,"enable":true,"event":"%s","urls":["%s"],"name":"%s"})",
                     desired[i].cid, desired[i].event, desired[i].url, desired[i].name);
            shellyPost(host, "/rpc/Webhook.Create", body);
            Serial.printf("Shelly: created webhook %s cid=%d on %s\n",
                          desired[i].event, desired[i].cid, host);
            changes++;
        }
    }

    if (changes == 0) {
        Serial.printf("Shelly: webhooks already configured on %s\n", host);
    }
    return true;
}

bool shellyRemoveScripts(const char* host) {
    JsonDocument doc;
    if (!shellyGet(host, "/rpc/Script.List", &doc)) {
        Serial.printf("Shelly: failed to list scripts on %s\n", host);
        return false;
    }

    JsonArray scripts = doc["scripts"];
    if (!scripts || scripts.size() == 0) {
        Serial.printf("Shelly: no scripts to remove on %s\n", host);
        return true;
    }

    for (JsonObject script : scripts) {
        int id = script["id"] | -1;
        bool running = script["running"] | false;
        const char* name = script["name"] | "unknown";

        if (running) {
            char body[32];
            snprintf(body, sizeof(body), R"({"id":%d})", id);
            shellyPost(host, "/rpc/Script.Stop", body);
            Serial.printf("Shelly: stopped script '%s' (id=%d) on %s\n", name, id, host);
        }

        char body[32];
        snprintf(body, sizeof(body), R"({"id":%d})", id);
        shellyPost(host, "/rpc/Script.Delete", body);
        Serial.printf("Shelly: deleted script '%s' (id=%d) on %s\n", name, id, host);
    }

    return true;
}
