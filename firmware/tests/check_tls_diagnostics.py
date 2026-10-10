"""Check the transparent TLS parser wrapper with the unchanged host library."""
from pathlib import Path
import re
import ssl
import subprocess
import tempfile

ROOT = Path(__file__).absolute().parents[2]
SOURCE = ROOT / ".tools/esp-idf-v5.5.5/components/mbedtls/mbedtls"
LIBRARIES = ROOT / ".tools/mbedtls-host-diagnostic/library"
with tempfile.TemporaryDirectory(prefix="sketch-tls-wrapper-") as temporary:
    work = Path(temporary)
    pem = re.search(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----",
                    (SOURCE / "framework/data_files/server2.crt").read_text(), re.S)[0]
    (work / "certificate.der").write_bytes(ssl.PEM_cert_to_DER_cert(pem))
    (work / "esp_log.h").write_text(
        "void test_log(const char *, const char *, ...);\n#define ESP_LOGI test_log\n")
    (work / "test.c").write_text(r'''
#include "mbedtls/x509_crt.h"
#include <assert.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
static unsigned records, calls;
void test_log(const char *tag, const char *format, ...) {
    char output[256]; va_list arguments;
    va_start(arguments, format); vsnprintf(output, sizeof(output), format, arguments); va_end(arguments);
    assert(!strcmp(tag, "device"));
    assert(strstr(output, "tls_certificate bytes=") == output);
    assert(strstr(output, "sha256=") && !strstr(output, "BEGIN CERTIFICATE"));
    ++records;
}
int __real_mbedtls_x509_crt_parse_der(mbedtls_x509_crt *chain, const unsigned char *bytes, size_t size) {
    ++calls; return mbedtls_x509_crt_parse_der(chain, bytes, size);
}
int __wrap_mbedtls_x509_crt_parse_der(mbedtls_x509_crt *, const unsigned char *, size_t);
int main(int argc, char **argv) {
    assert(argc == 2); unsigned char data[4096]; FILE *f = fopen(argv[1], "rb"); assert(f);
    size_t size = fread(data, 1, sizeof(data), f); fclose(f); assert(size > 0 && size < sizeof(data));
    for (int i = 0; i < 12; ++i) {
        size_t length = i % 2 ? 1 : size;
        mbedtls_x509_crt real, wrapped; mbedtls_x509_crt_init(&real); mbedtls_x509_crt_init(&wrapped);
        int expected = mbedtls_x509_crt_parse_der(&real, data, length);
        int actual = __wrap_mbedtls_x509_crt_parse_der(&wrapped, data, length);
        assert(expected == actual);
        if (!actual) assert(wrapped.raw.len == size && !memcmp(wrapped.raw.p, data, size));
        mbedtls_x509_crt_free(&real); mbedtls_x509_crt_free(&wrapped);
    }
    assert(calls == 12 && records == 8); puts("TLS parser delegation, result identity, bounded diagnostics: PASS");
}
''')
    subprocess.run(["clang", "-std=c11", "-g", "-Wall", "-Wextra", "-Werror",
                    "-fsanitize=address,undefined", "-I" + str(work), "-I" + str(SOURCE / "include"),
                    str(work / "test.c"), str(ROOT / "firmware/main/tls_diagnostics.c"),
                    str(LIBRARIES / "libmbedx509.a"), str(LIBRARIES / "libmbedcrypto.a"),
                    "-o", str(work / "test")], check=True)
    subprocess.run([str(work / "test"), str(work / "certificate.der")], check=True)
