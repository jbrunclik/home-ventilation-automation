#include "tuya_crypto.h"

#include <AES.h>
#include <GCM.h>
#include <SHA256.h>
#include <cstring>

void aes128GcmEncrypt(const uint8_t* key, const uint8_t* iv,
                      const uint8_t* plaintext, size_t len,
                      const uint8_t* aad, size_t aad_len,
                      uint8_t* out, uint8_t* tag) {
    GCM<AES128> gcm;
    gcm.setKey(key, 16);
    gcm.setIV(iv, 12);
    if (aad && aad_len > 0) {
        gcm.addAuthData(aad, aad_len);
    }
    gcm.encrypt(out, plaintext, len);
    gcm.computeTag(tag, 16);
}

void aes128GcmDecrypt(const uint8_t* key, const uint8_t* iv,
                      const uint8_t* ciphertext, size_t len,
                      uint8_t* out) {
    GCM<AES128> gcm;
    gcm.setKey(key, 16);
    gcm.setIV(iv, 12);
    gcm.decrypt(out, ciphertext, len);
}

void hmacSha256(const uint8_t* key, size_t key_len,
                const uint8_t* data, size_t data_len,
                uint8_t* out) {
    SHA256 sha;
    sha.resetHMAC(key, key_len);
    sha.update(data, data_len);
    sha.finalizeHMAC(key, key_len, out, 32);
}

void computeSessionKey(const uint8_t* device_key,
                       const uint8_t* local_nonce,
                       const uint8_t* remote_nonce,
                       uint8_t* session_key, uint8_t* session_tag) {
    // XOR nonces
    uint8_t xor_key[16];
    for (int i = 0; i < 16; i++) {
        xor_key[i] = local_nonce[i] ^ remote_nonce[i];
    }

    // Encrypt XOR result with device key using AES-GCM (protocol 3.5)
    uint8_t iv[12];
    memcpy(iv, local_nonce, 12);
    aes128GcmEncrypt(device_key, iv, xor_key, 16, nullptr, 0, session_key, session_tag);
}
