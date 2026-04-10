#pragma once

#include <cstddef>
#include <cstdint>

// AES-128-GCM encrypt. Ciphertext written to `out`, 16-byte tag to `tag`.
void aes128GcmEncrypt(const uint8_t* key, const uint8_t* iv,
                      const uint8_t* plaintext, size_t len,
                      const uint8_t* aad, size_t aad_len,
                      uint8_t* out, uint8_t* tag);

// AES-128-GCM decrypt. Plaintext written to `out`.
void aes128GcmDecrypt(const uint8_t* key, const uint8_t* iv,
                      const uint8_t* ciphertext, size_t len,
                      uint8_t* out);

// HMAC-SHA256. 32-byte result written to `out`.
void hmacSha256(const uint8_t* key, size_t key_len,
                const uint8_t* data, size_t data_len,
                uint8_t* out);

// Derive session key: XOR local_nonce with remote_nonce, encrypt with device key.
// Result written to `session_key` (16 bytes).
void computeSessionKey(const uint8_t* device_key,
                       const uint8_t* local_nonce,
                       const uint8_t* remote_nonce,
                       uint8_t* session_key, uint8_t* session_tag);
