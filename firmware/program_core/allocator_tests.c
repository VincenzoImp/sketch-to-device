/* Compile the actual ESP allocation branches; synthetic heap failure, real JS. */
#include "program_runtime.h"
#define ESP_PLATFORM 1
#include "program_runtime.c"
#include <stdio.h>

static bool fail_next;
static unsigned allocations, reallocations;
void *heap_caps_malloc(size_t size,uint32_t caps) {
    assert(caps==(MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));allocations++;
    if(fail_next){fail_next=false;return NULL;}return malloc(size);
}
void *heap_caps_realloc(void *ptr,size_t size,uint32_t caps) {
    assert(caps==(MALLOC_CAP_SPIRAM|MALLOC_CAP_8BIT));reallocations++;
    if(fail_next){fail_next=false;return NULL;}return realloc(ptr,size);
}
int64_t esp_timer_get_time(void) {
    struct timespec time;clock_gettime(CLOCK_MONOTONIC,&time);
    return (int64_t)time.tv_sec*1000000+time.tv_nsec/1000;
}
int main(void) {
    pr_runtime r={0};fail_next=true;
    assert(!js_alloc(&r,32)&&!r.payload&&!r.peak);
    unsigned char *p=js_alloc(&r,32);assert(p&&r.payload==32&&r.peak==32);
    assert((uintptr_t)p%_Alignof(max_align_t)==0);memset(p,0x5a,32);
    fail_next=true;assert(!js_resize(&r,p,64));
    assert(r.payload==32&&r.peak==32&&js_size(p)==32);
    for(unsigned i=0;i<32;i++)assert(p[i]==0x5a);
    p=js_resize(&r,p,128);assert(p&&r.payload==128&&r.peak==128);
    for(unsigned i=0;i<32;i++)assert(p[i]==0x5a);
    p=js_resize(&r,p,16);assert(p&&r.payload==16&&r.peak==128);
    assert(!js_resize(&r,p,PAYLOAD_LIMIT+1)&&r.payload==16&&js_size(p)==16);
    assert(!js_resize(&r,p,0)&&r.payload==0);
    p=js_zero(&r,8,4);assert(p&&r.payload==32);
    for(unsigned i=0;i<32;i++)assert(p[i]==0);
    assert(!js_zero(&r,SIZE_MAX,2)&&r.payload==32);js_release(&r,p);
    p=js_alloc(&r,PAYLOAD_LIMIT);assert(p&&r.payload==PAYLOAD_LIMIT);
    unsigned before=allocations;assert(!js_alloc(&r,1)&&allocations==before);
    js_release(&r,p);assert(!r.payload);
    const char *source="let n=0;app.onTick(()=>{n++;if(n<1)throw Error('state')});";
    pr_program program={source,strlen(source),NULL,0};
    for(unsigned i=0;i<100;i++) {
        const char *error=NULL;pr_runtime *runtime=pr_create(&program,(pr_clock){0},1,&error);assert(runtime&&!error);
        pr_set_activation(runtime,1);
        assert(pr_dispatch(runtime,(pr_event){1,1,PR_TICK,0,0},(pr_clock){1,0,PR_WALL_UNAVAILABLE}));
        assert(pr_get_metrics(runtime).engine_payload>0);
        pr_destroy(runtime); /* Internal residual-payload assertion must pass. */
    }
    assert(allocations>100&&reallocations>1);
    puts("{\"status\":\"target_allocator_tests_passed\",\"install_cycles\":100,\"heap\":\"synthetic_esp_api\",\"physical_execution\":false}");
    return 0;
}
