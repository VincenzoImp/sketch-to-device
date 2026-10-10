/* Reused tracked allocator and soft interrupt from the accepted engine probe. */
#define ALLOCATION_LIMIT (512u * 1024u)
#define ENGINE_LIMIT (256u * 1024u)
#define JOB_LIMIT 64
#define DEADLINE_US 50000

typedef union {
    max_align_t alignment;
    struct { size_t size; } info;
} allocation_header;

typedef struct {
    size_t allocated, peak;
    unsigned calls, jobs, events;
    int64_t deadline;
    int interrupted;
    uint32_t color, score;
} probe_state;

static int64_t now_us(void)
{
#ifdef ESP_PLATFORM
    return esp_timer_get_time();
#else
    struct timespec value;
    assert(clock_gettime(CLOCK_MONOTONIC, &value) == 0);
    return (int64_t)value.tv_sec * 1000000 + value.tv_nsec / 1000;
#endif
}

static void *tracked_malloc(void *opaque, size_t size)
{
    probe_state *state = opaque;
    if (!size || size > ALLOCATION_LIMIT - state->allocated
        || size > SIZE_MAX - sizeof(allocation_header)) return NULL;
    allocation_header *header = malloc(sizeof(*header) + size);
    if (!header) return NULL;
    header->info.size = size;
    state->allocated += size;
    if (state->allocated > state->peak) state->peak = state->allocated;
    return header + 1;
}

static void tracked_free(void *opaque, void *pointer)
{
    if (!pointer) return;
    probe_state *state = opaque;
    allocation_header *header = (allocation_header *)pointer - 1;
    assert(state->allocated >= header->info.size);
    state->allocated -= header->info.size;
    free(header);
}

static void *tracked_calloc(void *opaque, size_t count, size_t size)
{
    if (count && size > SIZE_MAX / count) return NULL;
    size *= count;
    void *result = tracked_malloc(opaque, size);
    if (result) memset(result, 0, size);
    return result;
}

static void *tracked_realloc(void *opaque, void *pointer, size_t size)
{
    if (!pointer) return tracked_malloc(opaque, size);
    if (!size) { tracked_free(opaque, pointer); return NULL; }
    probe_state *state = opaque;
    allocation_header *old = (allocation_header *)pointer - 1;
    size_t old_size = old->info.size;
    if (size > ALLOCATION_LIMIT - (state->allocated - old_size)
        || size > SIZE_MAX - sizeof(*old)) return NULL;
    allocation_header *next = realloc(old, sizeof(*old) + size);
    if (!next) return NULL;
    next->info.size = size;
    state->allocated = state->allocated - old_size + size;
    if (state->allocated > state->peak) state->peak = state->allocated;
    return next + 1;
}

static size_t tracked_size(const void *pointer)
{
    return pointer ? ((const allocation_header *)pointer - 1)->info.size : 0;
}

static int interrupt(JSRuntime *runtime, void *opaque)
{
    (void)runtime;
    probe_state *state = opaque;
    if (++state->calls > 1000 || now_us() >= state->deadline) {
        state->interrupted = 1;
        return 1;
    }
    return 0;
}

