/* Shared QuickJS/LVGL runtime. Generic drawing and events, no app behavior. */
#include "program_runtime.h"
#include "quickjs.h"
#include <assert.h>
#include <math.h>
#include <stddef.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#ifdef ESP_PLATFORM
#include "esp_timer.h"
#include "esp_heap_caps.h"
#endif

#define HEAP_LIMIT (256u * 1024u)
#define PAYLOAD_LIMIT (512u * 1024u)
#define REJECTIONS 16
#define JOB_LIMIT 64
#define DEADLINE_US 50000
typedef union { max_align_t align; struct { size_t size; } value; } allocation;
typedef enum { CMD_CLEAR, CMD_RECT, CMD_LINE, CMD_TEXT, CMD_IMAGE } command_type;
typedef struct {
    command_type type; int x, y, w, h, thickness, asset;
    uint32_t color; char text[PR_TEXT_BYTES + 1];
} command;
typedef struct { command items[PR_COMMANDS]; unsigned count; } batch;
typedef struct { char id[49]; uint8_t *pixels; lv_image_dsc_t image; } image_asset;
struct pr_runtime {
    JSRuntime *engine; JSContext *context;
    JSValue tick, pointer, rejected[REJECTIONS];
    unsigned rejected_count; bool rejection_overflow;
    size_t payload, peak, native_bytes;
    unsigned interrupt_calls, command_work, text_work, pixel_work;
    int64_t deadline; const char *fault;
    pr_diagnostic diagnostic;
    pr_clock clock; uint64_t activation, last_tick; uint32_t random;
    bool paused, drawing, staged, pending;
    batch build, candidate, ready;
    image_asset assets[PR_ASSETS]; size_t asset_count;
    lv_obj_t *root, *canvas, *scratch;
    uint16_t *front, *back;
    unsigned callbacks, frames, stale;
};
static int64_t real_us(void) {
#ifdef PR_TEST_CLOCK
    extern int64_t pr_test_time_us(void);
    return pr_test_time_us();
#elif defined(ESP_PLATFORM)
    return esp_timer_get_time();
#else
    struct timespec t; clock_gettime(CLOCK_MONOTONIC, &t);
    return (int64_t)t.tv_sec * 1000000 + t.tv_nsec / 1000;
#endif
}
static void *native_alloc(size_t n) {
#ifdef ESP_PLATFORM
    return heap_caps_malloc(n, MALLOC_CAP_SPIRAM | MALLOC_CAP_8BIT);
#else
    return malloc(n);
#endif
}
static void *js_alloc(void *opaque, size_t n) {
    pr_runtime *r = opaque;
    if (!n || n > PAYLOAD_LIMIT - r->payload || n > SIZE_MAX - sizeof(allocation)) return NULL;
    allocation *a = malloc(sizeof(*a) + n); if (!a) return NULL;
    a->value.size = n; r->payload += n; if (r->payload > r->peak) r->peak = r->payload;
    return a + 1;
}
static void js_release(void *opaque, void *p) {
    if (!p) return; pr_runtime *r = opaque; allocation *a = (allocation *)p - 1;
    assert(r->payload >= a->value.size); r->payload -= a->value.size; free(a);
}
static void *js_zero(void *o, size_t n, size_t s) {
    if (n && s > SIZE_MAX / n) return NULL;
    void *p = js_alloc(o, n*s); if (p) memset(p, 0, n*s); return p;
}
static void *js_resize(void *o, void *p, size_t n) {
    if (!p) return js_alloc(o, n); if (!n) { js_release(o,p); return NULL; }
    pr_runtime *r=o; allocation *a=(allocation *)p-1; size_t old=a->value.size;
    if (n>PAYLOAD_LIMIT-(r->payload-old) || n>SIZE_MAX-sizeof(*a)) return NULL;
    a=realloc(a,sizeof(*a)+n); if (!a) return NULL;
    a->value.size=n; r->payload=r->payload-old+n; if(r->payload>r->peak)r->peak=r->payload; return a+1;
}
static size_t js_size(const void *p) { return p ? ((const allocation *)p-1)->value.size : 0; }
static int interrupt(JSRuntime *engine, void *o) {
    (void)engine; pr_runtime *r=o;
    if (++r->interrupt_calls>1000 || real_us()>=r->deadline) { r->fault="execution_budget"; return 1; }
    return 0;
}
/* Inspect only primitive strings and data descriptors on genuine Errors.
 * JS_GetProperty/ToString would invoke app getters, proxies or coercion here. */
static bool diagnostic_string(JSContext *c,JSValueConst value,char *out,size_t cap,bool *truncated) {
    if(!JS_IsString(value))return false;
    size_t size=0;const char *text=JS_ToCStringLen(c,&size,value);
    if(!text){JS_FreeValue(c,JS_GetException(c));return false;}
    size_t copied=size<cap-1?size:cap-1;
    for(size_t i=0;i<copied;i++)out[i]=(text[i]>=' '&&text[i]<='~')?text[i]:' ';
    out[copied]=0;*truncated|=size>copied;JS_FreeCString(c,text);return true;
}
static JSValue diagnostic_data(JSContext *c,JSValueConst object,const char *key) {
    JSAtom atom=JS_NewAtom(c,key);if(atom==JS_ATOM_NULL){JS_FreeValue(c,JS_GetException(c));return JS_UNDEFINED;}
    JSPropertyDescriptor desc={0};int found=JS_GetOwnProperty(c,&desc,object,atom);JS_FreeAtom(c,atom);
    if(found<0){JS_FreeValue(c,JS_GetException(c));return JS_UNDEFINED;}
    if(!found)return JS_UNDEFINED;
    JSValue value=!(desc.flags&JS_PROP_GETSET)&&JS_IsString(desc.value)?JS_DupValue(c,desc.value):JS_UNDEFINED;
    JS_FreeValue(c,desc.value);JS_FreeValue(c,desc.getter);JS_FreeValue(c,desc.setter);return value;
}
static unsigned diagnostic_number(const char *text,size_t limit,size_t *offset) {
    unsigned n=0;size_t start=*offset;
    while(*offset<limit && text[*offset]>='0' && text[*offset]<='9') {
        unsigned digit=(unsigned)(text[(*offset)++]-'0');if(n>6553||(n==6553&&digit>6))return 0;n=n*10+digit;
    }
    return *offset>start?n:0;
}
static void diagnostic_location(JSContext *c,JSValueConst stack,pr_diagnostic *d) {
    if(!JS_IsString(stack))return;
    size_t size=0;const char *text=JS_ToCStringLen(c,&size,stack);
    if(!text){JS_FreeValue(c,JS_GetException(c));return;}
    size_t limit=size<1024?size:1024;d->truncated|=size>limit;
    for(size_t i=0;i+7<=limit;i++)if(!memcmp(text+i,"app.js:",7)) {
        size_t at=i+7;unsigned line=diagnostic_number(text,limit,&at);
        if(line){d->line=line;if(at<limit&&text[at]==':'){at++;d->column=diagnostic_number(text,limit,&at);}break;}
    }
    JS_FreeCString(c,text);
}
static void diagnostic_exception(pr_runtime *r,JSContext *c,JSValueConst exception) {
    pr_diagnostic *d=&r->diagnostic;if(d->exception_name[0])return;
    strcpy(d->exception_name,"ThrownValue");strcpy(d->message,"Non-Error exception; no object properties were evaluated");
    if(JS_IsString(exception)){strcpy(d->exception_name,"String");diagnostic_string(c,exception,d->message,sizeof(d->message),&d->truncated);return;}
    if(!JS_IsError(exception)||JS_IsProxy(exception))return;
    strcpy(d->exception_name,"Error");strcpy(d->message,"Exception details unavailable");
    JSValue message=diagnostic_data(c,exception,"message");
    diagnostic_string(c,message,d->message,sizeof(d->message),&d->truncated);JS_FreeValue(c,message);
    JSValue stack=diagnostic_data(c,exception,"stack");diagnostic_location(c,stack,d);JS_FreeValue(c,stack);
    JSValue global=JS_GetGlobalObject(c);JSClassID ordinary=JS_GetClassID(global);JS_FreeValue(c,global);
    JSValue object=JS_DupValue(c,exception);
    for(unsigned i=0;i<6 && JS_IsObject(object) && !JS_IsProxy(object) &&
        (JS_IsError(object)||JS_GetClassID(object)==ordinary);i++) {
        JSValue name=diagnostic_data(c,object,"name");
        bool copied=diagnostic_string(c,name,d->exception_name,sizeof(d->exception_name),&d->truncated);JS_FreeValue(c,name);
        if(copied)break;
        JSValue next=JS_GetPrototype(c,object);JS_FreeValue(c,object);object=next;
        if(JS_IsException(object)){JS_FreeValue(c,JS_GetException(c));break;}
    }
    JS_FreeValue(c,object);
}
static void diagnostic_pending(pr_runtime *r,JSContext *c) {
    JSValue exception=JS_GetException(c);diagnostic_exception(r,c,exception);JS_FreeValue(c,exception);
}
static void rejection(JSContext *c, JSValueConst promise, JSValueConst reason, bool handled, void *o) {
    (void)reason; pr_runtime *r=o;
    for(unsigned i=0;i<r->rejected_count;i++) if(JS_IsSameValue(c,r->rejected[i],promise)) {
        if(handled) { JS_FreeValue(c,r->rejected[i]); r->rejected[i]=r->rejected[--r->rejected_count]; }
        return;
    }
    if(handled)return;
    if(r->rejected_count==REJECTIONS) { r->rejection_overflow=true; return; }
    r->rejected[r->rejected_count++]=JS_DupValue(c,promise);
}
static int64_t checkpoint_begin(pr_runtime *r) {
    int64_t start=real_us();r->deadline=start+DEADLINE_US; r->interrupt_calls=0;
    r->command_work=r->text_work=r->pixel_work=0;
    r->drawing=r->staged=false; r->build.count=r->candidate.count=0;
    return start;
}
static bool checkpoint_end(pr_runtime *r, JSValue value) {
    bool ok=!JS_IsException(value); JS_FreeValue(r->context,value);
    if(!ok)diagnostic_pending(r,r->context);
    unsigned jobs=0;
    while(ok && JS_IsJobPending(r->engine)) {
        if(jobs++>=JOB_LIMIT || real_us()>=r->deadline) { r->fault="microtask_budget"; ok=false; break; }
        JSContext *c=NULL;
        if(JS_ExecutePendingJob(r->engine,&c)<0) { if(c)diagnostic_pending(r,c); ok=false; }
    }
    if(r->rejected_count || r->rejection_overflow) {
        if(r->rejected_count){JSValue reason=JS_PromiseResult(r->context,r->rejected[0]);diagnostic_exception(r,r->context,reason);JS_FreeValue(r->context,reason);}
        if(!r->fault)r->fault="unhandled_rejection";ok=false;
    }
    if(r->fault)ok=false;
    if(!ok) { if(!r->fault)r->fault="script_exception"; r->pending=false; return false; }
    if(r->staged) { r->ready=r->candidate; r->pending=true; }
    return true;
}
static JSValue bad(JSContext *c) { return JS_ThrowTypeError(c,"invalid device API argument or drawing budget exceeded"); }
static bool number(JSContext *c, JSValueConst v, int low, int high, int *out) {
    double d;
    if(!JS_IsNumber(v)||JS_ToFloat64(c,&d,v)||!isfinite(d)||floor(d)!=d||d<low||d>high)return false;
    *out=(int)d;return true;
}
static bool string(JSContext *c,JSValueConst v,char *out,size_t limit) {
    if(!JS_IsString(v))return false;size_t n;const char *s=JS_ToCStringLen(c,&n,v);if(!s)return false;
    bool ok=n<=limit&&!memchr(s,0,n);if(ok)memcpy(out,s,n+1);JS_FreeCString(c,s);return ok;
}
static bool color(JSContext *c,JSValueConst v,uint32_t *out) {
    char s[8];if(!string(c,v,s,7)||strlen(s)!=7||s[0]!='#')return false;uint32_t n=0;
    for(int i=1;i<7;i++) { char ch=s[i];int d=ch>='0'&&ch<='9'?ch-'0':ch>='a'&&ch<='f'?ch-'a'+10:ch>='A'&&ch<='F'?ch-'A'+10:-1;if(d<0)return false;n=n*16+(unsigned)d; }
    *out=n;return true;
}
static unsigned clipped_area(int x,int y,int w,int h) {
    int right=x+w,bottom=y+h;if(x<0)x=0;if(y<0)y=0;if(right>PR_WIDTH)right=PR_WIDTH;if(bottom>PR_HEIGHT)bottom=PR_HEIGHT;
    return right>x&&bottom>y?(unsigned)(right-x)*(unsigned)(bottom-y):0;
}
static bool append(pr_runtime *r,command q,unsigned pixels) {
    size_t text=strlen(q.text);
    if(r->command_work>=PR_COMMANDS||r->build.count>=PR_COMMANDS||pixels>PR_PIXEL_WORK-r->pixel_work||text>PR_CHECKPOINT_TEXT-r->text_work){r->fault="drawing_budget";return false;}
    r->command_work++;r->pixel_work+=pixels;r->text_work+=(unsigned)text;r->build.items[r->build.count++]=q;return true;
}
enum { G_BEGIN,G_RECT,G_LINE,G_TEXT,G_IMAGE,G_END };
static JSValue bad_graphics(JSContext *c,int operation) {
    static const char *const messages[]={
        "gfx.begin requires one #RRGGBB string and no already-open frame",
        "gfx.rect requires an open frame, integer x/y in -32768..32767, integer width/height in 0..32767, and #RRGGBB color",
        "gfx.line requires an open frame, integer endpoints x=0..319/y=0..431, #RRGGBB color, and integer thickness=1..32",
        "gfx.text requires an open frame, integer x/y in -32768..32767, text<=256 UTF-8 bytes without NUL, and #RRGGBB color",
        "gfx.image requires an open frame, a registered asset ID, and integer x/y in -32768..32767",
        "gfx.end requires an open frame and no arguments"
    };
    return JS_ThrowTypeError(c,"%s",messages[operation]);
}
static JSValue graphics(JSContext *c,JSValueConst self,int argc,JSValueConst *argv,int op) {
    (void)self;pr_runtime *r=JS_GetContextOpaque(c);command q={0};
    if(op==G_BEGIN) {
        if(argc!=1||r->drawing||!color(c,argv[0],&q.color))return bad_graphics(c,op);
        r->build.count=0;q.type=CMD_CLEAR;
        if(!append(r,q,PR_WIDTH*PR_HEIGHT))return bad_graphics(c,op);r->drawing=true;return JS_UNDEFINED;
    }
    if(!r->drawing)return bad_graphics(c,op);
    if(op==G_END) {
        if(argc)return bad_graphics(c,op);r->candidate=r->build;r->staged=true;r->drawing=false;return JS_UNDEFINED;
    }
    int args=op==G_RECT?5:op==G_LINE?6:op==G_TEXT?4:3;
    if(argc!=args)return bad_graphics(c,op);
    unsigned pixels=0;
    if(op==G_IMAGE) {
        char id[49];if(!string(c,argv[0],id,48)||!number(c,argv[1],-32768,32767,&q.x)||!number(c,argv[2],-32768,32767,&q.y))return bad_graphics(c,op);
        size_t i;for(i=0;i<r->asset_count;i++)if(!strcmp(id,r->assets[i].id))break;if(i==r->asset_count)return bad_graphics(c,op);
        q.type=CMD_IMAGE;q.asset=(int)i;q.w=r->assets[i].image.header.w;q.h=r->assets[i].image.header.h;
    } else {
        if(!number(c,argv[0],-32768,32767,&q.x)||!number(c,argv[1],-32768,32767,&q.y))return bad_graphics(c,op);
        if(op==G_TEXT) {
            q.type=CMD_TEXT;if(!string(c,argv[2],q.text,PR_TEXT_BYTES)||!color(c,argv[3],&q.color))return bad_graphics(c,op);
            /* The fixed Montserrat16 font, including replacement glyphs, is used on both targets. */
            q.w=PR_WIDTH;q.h=PR_HEIGHT;
        } else if(op==G_RECT) {
            q.type=CMD_RECT;if(!number(c,argv[2],0,32767,&q.w)||!number(c,argv[3],0,32767,&q.h)||!color(c,argv[4],&q.color))return bad_graphics(c,op);
        } else {
            q.type=CMD_LINE;
            /* Endpoint coordinates stay inside the viewport: bounds cover native line work. */
            if(q.x<0||q.x>=PR_WIDTH||q.y<0||q.y>=PR_HEIGHT||!number(c,argv[2],0,PR_WIDTH-1,&q.w)||!number(c,argv[3],0,PR_HEIGHT-1,&q.h)||!color(c,argv[4],&q.color)||!number(c,argv[5],1,32,&q.thickness))return bad_graphics(c,op);
            int x=q.x<q.w?q.x:q.w,y=q.y<q.h?q.y:q.h;
            pixels=clipped_area(x-q.thickness,y-q.thickness,abs(q.w-q.x)+2*q.thickness+1,abs(q.h-q.y)+2*q.thickness+1);
        }
    }
    if(op==G_TEXT)pixels=(unsigned)strlen(q.text)*16u*20u;
    else if(op!=G_LINE)pixels=clipped_area(q.x,q.y,q.w,q.h);
    if(!append(r,q,pixels))return bad_graphics(c,op);return JS_UNDEFINED;
}
enum { A_TICK,A_POINTER,A_NOW,A_WALL,A_RANDOM };
static JSValue application(JSContext *c,JSValueConst self,int argc,JSValueConst *argv,int op) {
    (void)self;pr_runtime *r=JS_GetContextOpaque(c);
    if(op==A_TICK||op==A_POINTER) {
        if(argc!=1||(!JS_IsNull(argv[0])&&!JS_IsFunction(c,argv[0])))return bad(c);
        JSValue *target=op==A_TICK?&r->tick:&r->pointer;
        JSValue next=JS_DupValue(c,argv[0]);JS_FreeValue(c,*target);*target=next;return JS_UNDEFINED;
    }
    if(argc)return bad(c);
    if(op==A_NOW)return JS_NewFloat64(c,(double)r->clock.monotonic_ms);
    if(op==A_RANDOM) { uint32_t n=r->random;n^=n<<13;n^=n>>17;n^=n<<5;r->random=n;return JS_NewFloat64(c,(double)n/4294967296.0); }
    JSValue result=JS_NewObject(c);
    if(JS_IsException(result))return result;
    const char *sources[]={"unavailable","estimated","synchronized"};
    if(JS_SetPropertyStr(c,result,"epochMs",r->clock.wall_source==PR_WALL_UNAVAILABLE?JS_NULL:JS_NewFloat64(c,(double)r->clock.epoch_ms))<0||JS_SetPropertyStr(c,result,"valid",JS_NewBool(c,r->clock.wall_source==PR_WALL_SYNCHRONIZED))<0||JS_SetPropertyStr(c,result,"source",JS_NewString(c,sources[r->clock.wall_source]))<0){JS_FreeValue(c,result);r->fault="allocation_failed";return JS_EXCEPTION;}return result;
}
static bool setup(pr_runtime *r) {
    JSContext *c=r->context;
    /* Date/performance would read the host clock. Explicit app clocks are injected. */
    if(JS_AddIntrinsicBaseObjects(c)<0||JS_AddIntrinsicEval(c)<0||JS_AddIntrinsicRegExp(c)<0||JS_AddIntrinsicJSON(c)<0||JS_AddIntrinsicProxy(c)<0||JS_AddIntrinsicMapSet(c)<0||JS_AddIntrinsicTypedArrays(c)<0||JS_AddIntrinsicPromise(c)<0||JS_AddIntrinsicWeakRef(c)<0||JS_AddIntrinsicDOMException(c)<0)return false;
    const char *gnames[]={"begin","rect","line","text","image","end"};int nargs[]={1,5,6,4,3,0};
    const char *anames[]={"onTick","onPointer","now","wallTime","random"};
    JSValue global=JS_GetGlobalObject(c),gfx=JS_NewObject(c),app=JS_NewObject(c);bool ok=!JS_IsException(gfx)&&!JS_IsException(app);
    for(int i=0;ok&&i<6;i++)ok=JS_SetPropertyStr(c,gfx,gnames[i],JS_NewCFunctionMagic(c,graphics,gnames[i],nargs[i],JS_CFUNC_generic_magic,i))>=0;
    for(int i=0;ok&&i<5;i++)ok=JS_SetPropertyStr(c,app,anames[i],JS_NewCFunctionMagic(c,application,anames[i],i<2?1:0,JS_CFUNC_generic_magic,i))>=0;
    if(ok) { ok=JS_SetPropertyStr(c,global,"gfx",gfx)>=0;gfx=JS_UNDEFINED; }
    if(ok) { ok=JS_SetPropertyStr(c,global,"app",app)>=0;app=JS_UNDEFINED; }
    JSValue math=JS_GetPropertyStr(c,global,"Math");
    if(ok)ok=JS_SetPropertyStr(c,math,"random",JS_NewCFunctionMagic(c,application,"random",0,JS_CFUNC_generic_magic,A_RANDOM))>=0;
    JS_FreeValue(c,math);JS_FreeValue(c,global);JS_FreeValue(c,gfx);JS_FreeValue(c,app);return ok;
}
static bool valid_clock(pr_clock c) { return c.monotonic_ms<=9007199254740991ULL&&c.epoch_ms>=0&&c.epoch_ms<=9007199254740991LL&&c.wall_source>=PR_WALL_UNAVAILABLE&&c.wall_source<=PR_WALL_SYNCHRONIZED; }
pr_runtime *pr_create_observed(const pr_program *p,pr_clock clock,uint32_t seed,const char **error,pr_diagnostic *diagnostic,pr_startup *startup) {
    pr_startup local={0};if(!startup)startup=&local;*startup=(pr_startup){.stage="setup"};
    int64_t start=real_us();
    if(diagnostic)*diagnostic=(pr_diagnostic){.phase="initialization"};
    if(error)*error="invalid_program";
    if(!p||!p->source||!p->source_size||p->source_size>PR_PACKAGE_BYTES||memchr(p->source,0,p->source_size)||p->asset_count>PR_ASSETS||(p->asset_count&&!p->assets)||!valid_clock(clock))return NULL;
    pr_runtime *r=calloc(1,sizeof(*r));if(!r){if(error)*error="allocation_failed";return NULL;}
    r->clock=clock;r->last_tick=clock.monotonic_ms;r->random=seed?seed:1;r->native_bytes=sizeof(*r);r->diagnostic.phase="initialization";
    r->tick=r->pointer=JS_UNDEFINED;size_t total=0;
    for(size_t i=0;i<p->asset_count;i++) {
        const pr_asset *a=&p->assets[i];
        if(!a->id||!a->rgba||!a->width||a->width>PR_WIDTH||!a->height||a->height>PR_HEIGHT||a->size!=(size_t)a->width*a->height*4||strlen(a->id)>48||a->size>PR_ASSET_BYTES-total)goto fail;
        image_asset *dest=&r->assets[i];dest->pixels=native_alloc(a->size);if(!dest->pixels)goto fail;
        r->asset_count++;r->native_bytes+=a->size;total+=a->size;strcpy(dest->id,a->id);
        /* LVGL ARGB8888 byte storage is B,G,R,A on the verified little-endian targets. */
        for(size_t j=0;j<a->size;j+=4) { dest->pixels[j]=a->rgba[j+2];dest->pixels[j+1]=a->rgba[j+1];dest->pixels[j+2]=a->rgba[j];dest->pixels[j+3]=a->rgba[j+3]; }
        dest->image.header=(lv_image_header_t){.magic=LV_IMAGE_HEADER_MAGIC,.cf=LV_COLOR_FORMAT_ARGB8888,.w=a->width,.h=a->height,.stride=a->width*4};
        dest->image.data_size=(uint32_t)a->size;dest->image.data=dest->pixels;
    }
    r->front=native_alloc(PR_WIDTH*PR_HEIGHT*2);r->back=native_alloc(PR_WIDTH*PR_HEIGHT*2);
    if(!r->front||!r->back)goto fail;
    memset(r->front,0,PR_WIDTH*PR_HEIGHT*2);memset(r->back,0,PR_WIDTH*PR_HEIGHT*2);r->native_bytes+=PR_WIDTH*PR_HEIGHT*4;
    static const JSMallocFunctions allocator={js_zero,js_alloc,js_release,js_resize,js_size};
    r->engine=JS_NewRuntime2(&allocator,r);if(!r->engine)goto fail;
    JS_SetMemoryLimit(r->engine,HEAP_LIMIT);JS_SetMaxStackSize(r->engine,32768);JS_SetHostPromiseRejectionTracker(r->engine,rejection,r);
    r->context=JS_NewContextRaw(r->engine);if(!r->context)goto fail;JS_SetContextOpaque(r->context,r);
    if(!setup(r))goto fail;
    char *source=malloc(p->source_size+1);if(!source)goto fail;memcpy(source,p->source,p->source_size);source[p->source_size]=0;
    startup->setup_us=(uint64_t)(real_us()-start);startup->stage="compile";
    start=checkpoint_begin(r);JS_SetInterruptHandler(r->engine,interrupt,r);
    JSValue compiled=JS_Eval(r->context,source,p->source_size,"app.js",JS_EVAL_TYPE_GLOBAL|JS_EVAL_FLAG_STRICT|JS_EVAL_FLAG_COMPILE_ONLY);free(source);
    startup->compile_us=(uint64_t)(real_us()-start);startup->compile_interrupts=r->interrupt_calls;
    if(JS_IsException(compiled)){diagnostic_pending(r,r->context);JS_FreeValue(r->context,compiled);if(!r->fault)r->fault="script_exception";goto fail;}
    if(r->fault || startup->compile_us>=DEADLINE_US){r->fault="execution_budget";JS_FreeValue(r->context,compiled);goto fail;}
    startup->stage="evaluate";start=checkpoint_begin(r);
    /* EvalFunction consumes the compiled value even when execution throws. */
    JSValue result=JS_EvalFunction(r->context,compiled);bool ok=checkpoint_end(r,result);
    startup->evaluate_us=(uint64_t)(real_us()-start);startup->evaluate_interrupts=r->interrupt_calls;
    if(!ok)goto fail;
    startup->stage="ready";
    if(error)*error=NULL;return r;
fail:
    if(!strcmp(startup->stage,"setup"))startup->setup_us=(uint64_t)(real_us()-start);
    if(error)*error=r->fault?r->fault:"allocation_or_program_error";
    if(diagnostic)*diagnostic=r->diagnostic;pr_destroy(r);return NULL;
}
pr_runtime *pr_create_diagnostic(const pr_program *p,pr_clock clock,uint32_t seed,const char **error,pr_diagnostic *diagnostic) {
    return pr_create_observed(p,clock,seed,error,diagnostic,NULL);
}
pr_runtime *pr_create(const pr_program *p,pr_clock clock,uint32_t seed,const char **error) {
    return pr_create_diagnostic(p,clock,seed,error,NULL);
}
bool pr_get_diagnostic(const pr_runtime *r,pr_diagnostic *out) {
    if(!r||!out)return false;*out=r->diagnostic;return out->exception_name[0]!=0;
}
static void plain(lv_obj_t *o) { lv_obj_remove_style_all(o);lv_obj_set_pos(o,0,0);lv_obj_set_size(o,PR_WIDTH,PR_HEIGHT);lv_obj_remove_flag(o,LV_OBJ_FLAG_SCROLLABLE); }
bool pr_attach(pr_runtime *r,lv_obj_t *parent) {
    if(!r||r->root||r->fault||!parent)return false;
    r->root=lv_obj_create(parent);if(!r->root)return false;plain(r->root);lv_obj_add_flag(r->root,LV_OBJ_FLAG_HIDDEN);
    r->canvas=lv_canvas_create(r->root);r->scratch=lv_canvas_create(r->root);
    if(!r->canvas||!r->scratch){pr_detach(r);return false;}plain(r->canvas);plain(r->scratch);lv_obj_add_flag(r->scratch,LV_OBJ_FLAG_HIDDEN);
    lv_canvas_set_buffer(r->canvas,r->front,PR_WIDTH,PR_HEIGHT,LV_COLOR_FORMAT_RGB565);
    lv_canvas_set_buffer(r->scratch,r->back,PR_WIDTH,PR_HEIGHT,LV_COLOR_FORMAT_RGB565);
    return pr_present(r);
}
bool pr_present(pr_runtime *r) {
    if(!r||!r->root||r->fault)return false;if(!r->pending)return true;
    lv_layer_t layer;lv_canvas_init_layer(r->scratch,&layer);
    for(unsigned i=0;i<r->ready.count;i++) {
        command *q=&r->ready.items[i];lv_area_t area={q->x,q->y,q->x+q->w-1,q->y+q->h-1};
        if(q->type==CMD_CLEAR)lv_canvas_fill_bg(r->scratch,lv_color_hex(q->color),LV_OPA_COVER);
        else if(q->type==CMD_RECT&&q->w&&q->h) { lv_draw_rect_dsc_t d;lv_draw_rect_dsc_init(&d);d.bg_color=lv_color_hex(q->color);d.bg_opa=LV_OPA_COVER;lv_draw_rect(&layer,&d,&area); }
        else if(q->type==CMD_LINE) { lv_draw_line_dsc_t d;lv_draw_line_dsc_init(&d);d.p1=(lv_point_precise_t){q->x,q->y};d.p2=(lv_point_precise_t){q->w,q->h};d.width=q->thickness;d.color=lv_color_hex(q->color);lv_draw_line(&layer,&d); }
        else if(q->type==CMD_TEXT) { lv_draw_label_dsc_t d;lv_draw_label_dsc_init(&d);d.text=q->text;d.font=&lv_font_montserrat_16;d.color=lv_color_hex(q->color);lv_draw_label(&layer,&d,&area); }
        else if(q->type==CMD_IMAGE) { lv_draw_image_dsc_t d;lv_draw_image_dsc_init(&d);d.src=&r->assets[q->asset].image;lv_draw_image(&layer,&d,&area); }
    }
    lv_canvas_finish_layer(r->scratch,&layer);
    uint16_t *p=r->front;r->front=r->back;r->back=p;
    lv_canvas_set_buffer(r->canvas,r->front,PR_WIDTH,PR_HEIGHT,LV_COLOR_FORMAT_RGB565);
    lv_canvas_set_buffer(r->scratch,r->back,PR_WIDTH,PR_HEIGHT,LV_COLOR_FORMAT_RGB565);
    lv_obj_invalidate(r->canvas);r->pending=false;r->frames++;return true;
}
lv_obj_t *pr_root(pr_runtime *r){return r?r->root:NULL;}
void pr_detach(pr_runtime *r){if(r&&r->root){lv_obj_delete(r->root);r->root=r->canvas=r->scratch=NULL;}}
void pr_destroy(pr_runtime *r) {
    if(!r)return;assert(!r->root);
    if(r->context){JS_SetHostPromiseRejectionTracker(r->engine,NULL,NULL);JS_FreeValue(r->context,r->tick);JS_FreeValue(r->context,r->pointer);for(unsigned i=0;i<r->rejected_count;i++)JS_FreeValue(r->context,r->rejected[i]);JS_FreeContext(r->context);}
    if(r->engine)JS_FreeRuntime(r->engine);assert(!r->payload);
    for(size_t i=0;i<r->asset_count;i++)free(r->assets[i].pixels);free(r->front);free(r->back);free(r);
}
bool pr_dispatch(pr_runtime *r,pr_event event,pr_clock clock) {
    if(!r||r->fault)return false;
    if(event.activation!=r->activation){r->stale++;return true;}
    if(!valid_clock(clock)||clock.monotonic_ms<r->clock.monotonic_ms||event.timestamp_ms>clock.monotonic_ms||event.type<PR_TICK||event.type>PR_CANCEL){r->fault="invalid_event";return false;}
    r->clock=clock;if(r->paused)return true;
    if(event.type!=PR_TICK&&(event.x<0||event.x>=PR_WIDTH||event.y<0||event.y>=PR_HEIGHT)){r->fault="invalid_event";return false;}
    JSValue callback=JS_DupValue(r->context,event.type==PR_TICK?r->tick:r->pointer);
    uint64_t delta=clock.monotonic_ms-r->last_tick;if(event.type==PR_TICK)r->last_tick=clock.monotonic_ms;
    if(!JS_IsFunction(r->context,callback)){JS_FreeValue(r->context,callback);return true;}
    r->diagnostic.phase=event.type==PR_TICK?"tick":"pointer";
    checkpoint_begin(r);JSContext *c=r->context;JSValue arg=JS_NewObject(c);
    bool allocated=!JS_IsException(arg);
    if(allocated&&event.type==PR_TICK){allocated=JS_SetPropertyStr(c,arg,"now",JS_NewFloat64(c,(double)clock.monotonic_ms))>=0&&JS_SetPropertyStr(c,arg,"delta",JS_NewFloat64(c,(double)delta))>=0;}
    else if(allocated){const char *phases[]={"tick","down","move","up","cancel"};allocated=JS_SetPropertyStr(c,arg,"type",JS_NewString(c,phases[event.type]))>=0&&JS_SetPropertyStr(c,arg,"x",JS_NewInt32(c,event.x))>=0&&JS_SetPropertyStr(c,arg,"y",JS_NewInt32(c,event.y))>=0&&JS_SetPropertyStr(c,arg,"time",JS_NewFloat64(c,(double)event.timestamp_ms))>=0;}
    if(!allocated)r->fault="allocation_failed";
    JSValue result=allocated?JS_Call(c,callback,JS_UNDEFINED,1,&arg):JS_EXCEPTION;
    JS_FreeValue(c,arg);JS_FreeValue(c,callback);r->callbacks++;return checkpoint_end(r,result);
}
void pr_set_activation(pr_runtime *r,uint64_t activation){if(r)r->activation=activation;}
void pr_pause(pr_runtime *r){if(r)r->paused=true;}
void pr_resume(pr_runtime *r,pr_clock clock){if(r&&valid_clock(clock)&&clock.monotonic_ms>=r->clock.monotonic_ms){r->paused=false;r->clock=clock;r->last_tick=clock.monotonic_ms;}}
pr_metrics pr_get_metrics(const pr_runtime *r){return (pr_metrics){r->callbacks,r->frames,r->stale,r->payload,r->peak,r->native_bytes,r->fault};}
const uint16_t *pr_pixels(const pr_runtime *r){return r?r->front:NULL;}
