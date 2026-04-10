#include "tuya_client.h"
#include "tuya_crypto.h"

#include <ArduinoJson.h>
#include <WiFi.h>
#include <cstring>

static constexpr uint16_t TUYA_PORT = 6668;
static constexpr int SOCKET_TIMEOUT_MS = 5000;
static constexpr int CONNECT_RETRIES = 3;
static constexpr size_t BUF_SIZE = 512;

// Fixed local nonce (same as EspTuya/tinytuya)
static const uint8_t LOCAL_NONCE[16] = {
    0x30, 0x31, 0x32, 0x33, 0x34, 0x35, 0x36, 0x37,
    0x38, 0x39, 0x61, 0x62, 0x63, 0x64, 0x65, 0x66
};

// 6699 protocol prefix/suffix
static const uint8_t PREFIX_6699[4] = {0x00, 0x00, 0x66, 0x99};
static const uint8_t SUFFIX_6699[4] = {0x00, 0x00, 0x99, 0x66};

// Parse device local_key string to 16-byte key
static void parseLocalKey(const char* str, uint8_t* key) {
    memset(key, 0, 16);
    size_t len = strlen(str);
    if (len > 16) len = 16;
    memcpy(key, str, len);
}

// Build big-endian uint32 into buffer
static void putBE32(uint8_t* buf, uint32_t val) {
    buf[0] = (val >> 24) & 0xFF;
    buf[1] = (val >> 16) & 0xFF;
    buf[2] = (val >> 8) & 0xFF;
    buf[3] = val & 0xFF;
}

// Read big-endian uint32 from buffer
static uint32_t getBE32(const uint8_t* buf) {
    return ((uint32_t)buf[0] << 24) | ((uint32_t)buf[1] << 16) |
           ((uint32_t)buf[2] << 8) | (uint32_t)buf[3];
}

// Build a 6699 message: [prefix 4][unknown 2][seq 4][cmd 4][datalen 4][iv 12][payload][tag 16][suffix 4]
// datalen = 12 (IV) + payload_len + 16 (tag)
static int buildMessage6699(uint8_t* out, uint32_t seq, uint32_t cmd,
                            const uint8_t* payload, size_t payload_len,
                            const uint8_t* key) {
    // Header: 14 bytes (unknown 2 + seq 4 + cmd 4 + datalen 4)
    uint8_t header[14];
    memset(header, 0, 2);  // unknown
    putBE32(header + 2, seq);
    putBE32(header + 6, cmd);
    uint32_t datalen = 12 + payload_len + 16;
    putBE32(header + 10, datalen);

    uint8_t iv[12];
    memcpy(iv, LOCAL_NONCE, 12);

    uint8_t encrypted[BUF_SIZE];
    uint8_t tag[16];
    aes128GcmEncrypt(key, iv, payload, payload_len, header, 14, encrypted, tag);

    int pos = 0;
    memcpy(out + pos, PREFIX_6699, 4); pos += 4;
    memcpy(out + pos, header, 14); pos += 14;
    memcpy(out + pos, iv, 12); pos += 12;
    memcpy(out + pos, encrypted, payload_len); pos += payload_len;
    memcpy(out + pos, tag, 16); pos += 16;
    memcpy(out + pos, SUFFIX_6699, 4); pos += 4;
    return pos;
}

// Parse a received 6699 message. Extracts and decrypts payload.
// Returns payload length, or -1 on error.
static int parseMessage6699(const uint8_t* msg, size_t msg_len,
                            const uint8_t* key, uint8_t* payload_out) {
    if (msg_len < 50) return -1;  // minimum: 4+14+12+0+16+4
    if (memcmp(msg, PREFIX_6699, 4) != 0) return -1;

    // Header at offset 4, 14 bytes
    uint32_t datalen = getBE32(msg + 4 + 10);
    size_t expected = 4 + 14 + datalen + 4;
    if (msg_len < expected) return -1;

    // IV at offset 18, 12 bytes
    uint8_t iv[12];
    memcpy(iv, msg + 18, 12);

    // Encrypted payload starts after IV
    size_t enc_len = datalen - 12 - 16;
    const uint8_t* ciphertext = msg + 30;

    aes128GcmDecrypt(key, iv, ciphertext, enc_len, payload_out);
    return (int)enc_len;
}

// Receive a complete message from the TCP client.
// Reads until suffix is found or timeout.
static int receiveMsg(WiFiClient& client, uint8_t* buf, size_t buf_size) {
    unsigned long start = millis();
    int pos = 0;

    while ((millis() - start) < (unsigned long)SOCKET_TIMEOUT_MS) {
        while (client.available() && pos < (int)buf_size) {
            buf[pos++] = client.read();
        }
        // Check if we have a complete message (found suffix)
        if (pos >= 8) {
            // Check for 6699 suffix at end
            if (buf[pos - 4] == 0x00 && buf[pos - 3] == 0x00 &&
                buf[pos - 2] == 0x99 && buf[pos - 1] == 0x66) {
                return pos;
            }
        }
        if (pos > 0 && !client.available()) {
            delay(10);
            if (!client.available()) return pos;
        }
        delay(1);
    }
    return pos;
}

// Connect TCP to the Tuya device
static bool tcpConnect(WiFiClient& client, const char* ip) {
    for (int i = 0; i < CONNECT_RETRIES; i++) {
        if (client.connect(ip, TUYA_PORT, SOCKET_TIMEOUT_MS)) {
            return true;
        }
        delay(50);
    }
    return false;
}

// Perform key negotiation (protocol 3.5).
// Returns true if session_key was derived successfully.
static bool negotiateKey(WiFiClient& client, const uint8_t* device_key,
                         uint8_t* session_key) {
    uint8_t out_buf[BUF_SIZE];
    uint8_t in_buf[BUF_SIZE];

    // Message 1: Send local_nonce, command 0x03
    int msg_len = buildMessage6699(out_buf, 1, 0x03, LOCAL_NONCE, 16, device_key);
    client.write(out_buf, msg_len);

    // Receive response with remote_nonce
    int recv_len = receiveMsg(client, in_buf, BUF_SIZE);
    if (recv_len <= 0) {
        Serial.println("Tuya: no response to key negotiation");
        return false;
    }

    uint8_t remote_nonce[16];
    uint8_t decrypted[BUF_SIZE];
    int dec_len = parseMessage6699(in_buf, recv_len, device_key, decrypted);
    if (dec_len < 16) {
        Serial.printf("Tuya: key response too short (%d bytes)\n", dec_len);
        return false;
    }

    // Extract remote nonce — strip leading control chars (protocol 3.5 padding)
    int offset = 0;
    while (offset < dec_len && decrypted[offset] < 0x20 && (dec_len - offset) > 16) {
        offset++;
    }
    memcpy(remote_nonce, decrypted + offset, 16);

    // Message 2: Finalize — send HMAC-SHA256 of remote_nonce, command 0x05
    uint8_t hmac_result[32];
    hmacSha256(device_key, 16, remote_nonce, 16, hmac_result);

    msg_len = buildMessage6699(out_buf, 2, 0x05, hmac_result, 32, device_key);
    client.write(out_buf, msg_len);
    // No response expected for message 2

    // Derive session key
    uint8_t tag[16];
    computeSessionKey(device_key, LOCAL_NONCE, remote_nonce, session_key, tag);

    return true;
}

// Send status query (command 0x10), parse DPS response.
static bool queryStatus(WiFiClient& client, const uint8_t* session_key,
                        TuyaReading& out) {
    uint8_t out_buf[BUF_SIZE];
    uint8_t in_buf[BUF_SIZE];

    // Send status request with empty payload "{}"
    const uint8_t payload[] = {0x7B, 0x7D};  // "{}"
    int msg_len = buildMessage6699(out_buf, 3, 0x10, payload, 2, session_key);
    client.write(out_buf, msg_len);

    // Receive status response
    int recv_len = receiveMsg(client, in_buf, BUF_SIZE);
    if (recv_len <= 0) {
        Serial.println("Tuya: no status response");
        return false;
    }

    uint8_t decrypted[BUF_SIZE];
    int dec_len = parseMessage6699(in_buf, recv_len, session_key, decrypted);
    if (dec_len <= 0) {
        Serial.println("Tuya: failed to decrypt status");
        return false;
    }

    // Strip version prefix "3.x" + nulls before JSON
    int json_start = 0;
    for (int i = 0; i < dec_len; i++) {
        if (decrypted[i] == '{') {
            json_start = i;
            break;
        }
    }
    decrypted[dec_len] = '\0';

    // Parse JSON
    JsonDocument doc;
    DeserializationError err = deserializeJson(doc, (const char*)(decrypted + json_start));
    if (err) {
        Serial.printf("Tuya: JSON error: %s\n", err.c_str());
        Serial.printf("Tuya: raw payload: %s\n", (const char*)(decrypted + json_start));
        return false;
    }

    // Extract DPS values — may be at root or nested under "dps"
    JsonObject dps;
    if (doc["dps"].is<JsonObject>()) {
        dps = doc["dps"];
    } else if (doc["result"].is<JsonObject>() && doc["result"]["dps"].is<JsonObject>()) {
        dps = doc["result"]["dps"];
    }

    if (dps.isNull()) {
        Serial.println("Tuya: no DPS in response");
        return false;
    }

    out.co2 = dps["2"] | -1;
    out.temperature = dps["18"] | -1.0f;
    out.pm25 = dps["101"] | -1.0f;
    out.valid = (out.co2 >= 0);

    return out.valid;
}

// Send DPS command (command 0x0D) to set data points.
static bool sendDpsCommand(WiFiClient& client, const uint8_t* session_key,
                           const char* dps_json) {
    uint8_t out_buf[BUF_SIZE];
    uint8_t in_buf[BUF_SIZE];

    // Build payload: version prefix + protocol wrapper + DPS
    // Format: "3.5" + 13 nulls + {"protocol":5,"t":TIMESTAMP,"data":{"dps":{DPS_JSON}}}
    char payload[256];
    int pos = 0;

    // Version prefix
    payload[pos++] = '3';
    payload[pos++] = '.';
    payload[pos++] = '5';
    for (int i = 0; i < 13; i++) payload[pos++] = '\0';

    // JSON wrapper
    unsigned long t = time(nullptr);
    pos += snprintf(payload + pos, sizeof(payload) - pos,
                    "{\"protocol\":5,\"t\":%lu,\"data\":{\"dps\":{%s}}}",
                    t, dps_json);

    int msg_len = buildMessage6699(out_buf, 3, 0x0D,
                                   (const uint8_t*)payload, pos, session_key);
    client.write(out_buf, msg_len);

    // Read acknowledgment (best-effort)
    receiveMsg(client, in_buf, BUF_SIZE);
    return true;
}

bool tuyaPollSensor(const TuyaSensorConfig& config, TuyaReading& out) {
    out = TuyaReading{};

    uint8_t device_key[16];
    parseLocalKey(config.local_key, device_key);

    WiFiClient client;
    if (!tcpConnect(client, config.ip)) {
        Serial.printf("Tuya: failed to connect to %s\n", config.ip);
        return false;
    }

    uint8_t session_key[16];
    if (!negotiateKey(client, device_key, session_key)) {
        client.stop();
        return false;
    }

    bool ok = queryStatus(client, session_key, out);
    client.stop();

    if (ok) {
        Serial.printf("Tuya: %s CO2=%d ppm, temp=%.0f, pm25=%.0f\n",
                      config.ip, out.co2, out.temperature, out.pm25);
    }
    return ok;
}

bool tuyaConfigureSensor(const TuyaSensorConfig& config) {
    uint8_t device_key[16];
    parseLocalKey(config.local_key, device_key);

    WiFiClient client;
    if (!tcpConnect(client, config.ip)) {
        Serial.printf("Tuya: failed to connect to %s for config\n", config.ip);
        return false;
    }

    uint8_t session_key[16];
    if (!negotiateKey(client, device_key, session_key)) {
        client.stop();
        return false;
    }

    // Disable alarm (DP 13 → false), dim alarm LED (DP 17 → 0)
    sendDpsCommand(client, session_key, "\"13\":false,\"17\":0");
    client.stop();

    Serial.printf("Tuya: configured %s (%s): alarm off, screen sleep off\n",
                  config.device_id, config.ip);
    return true;
}
