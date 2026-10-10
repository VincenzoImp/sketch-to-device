#include "esp_log.h"
#include "mbedtls/sha256.h"
#include "mbedtls/x509_crt.h"
#include <stdatomic.h>
#include <stdio.h>

int __real_mbedtls_x509_crt_parse_der(mbedtls_x509_crt *chain,
                                    const unsigned char *bytes, size_t size);

/* Observe the unchanged parser, without disclosing certificate contents or
 * changing trust decisions. A boot emits at most eight diagnostic records. */
int __wrap_mbedtls_x509_crt_parse_der(mbedtls_x509_crt *chain,
                                    const unsigned char *bytes, size_t size) {
    static atomic_uint calls;
    int result = __real_mbedtls_x509_crt_parse_der(chain, bytes, size);
    if (atomic_fetch_add_explicit(&calls, 1, memory_order_relaxed) < 8) {
        unsigned char digest[32];
        char hex[65] = {0};
        int hashed = mbedtls_sha256(bytes, size, digest, 0);
        if (!hashed)
            for (int i = 0; i < 32; ++i) snprintf(hex + 2 * i, 3, "%02x", digest[i]);
        ESP_LOGI("device", "tls_certificate bytes=%u result=%d sha256=%s",
                 (unsigned)size, result, hashed ? "unavailable" : hex);
    }
    return result;
}
