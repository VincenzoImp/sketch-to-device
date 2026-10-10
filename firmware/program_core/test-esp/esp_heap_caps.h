#pragma once
#include <stddef.h>
#include <stdint.h>
/* Values from the pinned IDF5.5.5 header. Test heap storage is ordinary host
 * memory; these functions verify the actual target allocator's capability API. */
#define MALLOC_CAP_8BIT (1 << 2)
#define MALLOC_CAP_SPIRAM (1 << 10)
void *heap_caps_malloc(size_t, uint32_t);
void *heap_caps_realloc(void *, size_t, uint32_t);
