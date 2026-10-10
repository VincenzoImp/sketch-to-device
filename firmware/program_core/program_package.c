#include "program_package.h"
#include "mbedtls/base64.h"
#include "mbedtls/sha256.h"
#include <math.h>
#include <stdlib.h>
#include <string.h>

void pr_sha256(const uint8_t *p,size_t n,char hex[65]) {
    unsigned char digest[32];mbedtls_sha256(p,n,digest,0);static const char h[]="0123456789abcdef";
    for(unsigned i=0;i<32;i++){hex[i*2]=h[digest[i]>>4];hex[i*2+1]=h[digest[i]&15];}hex[64]=0;
}
static bool utf8(const unsigned char *s,size_t n) {
    for(size_t i=0;i<n;) {
        uint32_t ch=s[i++];unsigned need=0;uint32_t min=0;
        if(!ch)return false;if(ch<128)continue;
        if(ch>=0xc2&&ch<=0xdf){need=1;min=0x80;ch&=31;}
        else if(ch>=0xe0&&ch<=0xef){need=2;min=0x800;ch&=15;}
        else if(ch>=0xf0&&ch<=0xf4){need=3;min=0x10000;ch&=7;}else return false;
        if(need>n-i)return false;
        while(need--){unsigned c=s[i++];if((c&0xc0)!=0x80)return false;ch=(ch<<6)|(c&63);}
        if(ch<min||ch>0x10ffff||(ch>=0xd800&&ch<=0xdfff))return false;
    }return true;
}
static bool lex(const char *s,size_t n) {
    if(!utf8((const unsigned char *)s,n))return false;
    unsigned depth=0;bool quoted=false;
    for(size_t i=0;i<n;i++) {
        unsigned char c=(unsigned char)s[i];
        if(quoted) {
            if(c=='"'){quoted=false;continue;}
            if(c<32)return false;
            if(c=='\\') {
                if(++i==n)return false;
                if(s[i]=='u') {
                    if(n-i<5)return false;
                    if(!memcmp(s+i+1,"0000",4))return false;
                    i+=4;
                }
            }
        } else if(c>=128||(c<32&&c!='\t'&&c!='\n'&&c!='\r'))return false;
        else if(c=='"')quoted=true;
        else if(c=='{'||c=='['){if(++depth>12)return false;}
        else if(c=='}'||c==']'){if(!depth)return false;depth--;}
        else if(c=='-'||(c>='0'&&c<='9')) {
            if(c=='-'){if(++i==n)return false;c=(unsigned char)s[i];}
            if(c<'0'||c>'9')return false;
            if(c=='0'&&i+1<n&&s[i+1]>='0'&&s[i+1]<='9')return false;
            while(i+1<n&&s[i+1]>='0'&&s[i+1]<='9')i++;
            if(i+1<n&&(s[i+1]=='.'||s[i+1]=='e'||s[i+1]=='E'))return false;
        }
    }return !quoted&&!depth;
}
static bool tree(const cJSON *v) {
    if(cJSON_IsString(v)&&(!v->valuestring||!utf8((const unsigned char *)v->valuestring,strlen(v->valuestring))))return false;
    if(cJSON_IsNumber(v)&&(!isfinite(v->valuedouble)||floor(v->valuedouble)!=v->valuedouble))return false;
    for(const cJSON *a=v->child;a;a=a->next) {
        if(cJSON_IsObject(v)) {
            if(!a->string)return false;
            for(const cJSON *b=v->child;b!=a;b=b->next)if(!strcmp(a->string,b->string))return false;
        }
        if(!tree(a))return false;
    }return true;
}
cJSON *pr_json_parse(const void *bytes,size_t n,size_t maximum) {
    if(!bytes||!n||n>maximum||!lex(bytes,n))return NULL;
    char *copy=malloc(n+1);if(!copy)return NULL;memcpy(copy,bytes,n);copy[n]=0;
    cJSON *v=cJSON_ParseWithLengthOpts(copy,n+1,NULL,1);free(copy);
    if(v&&!tree(v)){cJSON_Delete(v);v=NULL;}return v;
}
static bool fields(const cJSON *v,const char *const *keys,size_t count) {
    if(!cJSON_IsObject(v)||cJSON_GetArraySize(v)!=(int)count)return false;
    for(size_t i=0;i<count;i++)if(!cJSON_GetObjectItemCaseSensitive(v,keys[i]))return false;return true;
}
static const char *str(const cJSON *v,const char *key){const cJSON *x=cJSON_GetObjectItemCaseSensitive(v,key);return cJSON_IsString(x)?x->valuestring:NULL;}
static bool integer(const cJSON *v,const char *key,int low,int high,int *out){const cJSON *x=cJSON_GetObjectItemCaseSensitive(v,key);if(!cJSON_IsNumber(x)||x->valuedouble<low||x->valuedouble>high)return false;*out=(int)x->valuedouble;return true;}
static bool identifier(const char *s){if(!s||!*s||strlen(s)>48||*s<'a'||*s>'z')return false;for(;*s;s++)if(!(*s>='a'&&*s<='z')&&!(*s>='0'&&*s<='9')&&*s!='_'&&*s!='-')return false;return true;}
static bool eq(const cJSON *v,const char *key,const char *value){const char *s=str(v,key);return s&&!strcmp(s,value);}
void pr_package_free(pr_package *p){if(!p)return;for(size_t i=0;i<p->program.asset_count;i++)free((void *)p->assets[i].rgba);cJSON_Delete(p->document);memset(p,0,sizeof(*p));}
bool pr_package_parse(const void *bytes,size_t size,pr_package *p,const char **error) {
    if(!p)return false;memset(p,0,sizeof(*p));if(error)*error="invalid_package";
    cJSON *v=pr_json_parse(bytes,size,PR_PACKAGE_BYTES);if(!v)return false;p->document=v;
    static const char *const keys[]={"schema_version","app_id","name","version","runtime","sdk","profile","requires","source","assets"};
    int schema,version;
    if(!fields(v,keys,10)||!integer(v,"schema_version",2,2,&schema)||!integer(v,"version",1,2147483647,&version)||!identifier(str(v,"app_id"))||!eq(v,"runtime","quickjs-ng-0.14.0")||!eq(v,"sdk","device-js-1")||!eq(v,"profile","p4-canvas-1"))goto fail;
    const char *name=str(v,"name"),*source=str(v,"source");if(!name||!strlen(name)||strlen(name)>48||!source||!strlen(source)||strlen(source)>PR_PACKAGE_BYTES)goto fail;
    for(const char *s=name;*s;s++)if(*s<32||*s>126)goto fail;
    const cJSON *modules=cJSON_GetObjectItemCaseSensitive(v,"requires");if(!cJSON_IsArray(modules)||cJSON_GetArraySize(modules)>3)goto fail;
    unsigned mask=0;
    for(const cJSON *m=modules->child;m;m=m->next){if(!cJSON_IsString(m))goto fail;unsigned bit=!strcmp(m->valuestring,"canvas")?1:!strcmp(m->valuestring,"input")?2:!strcmp(m->valuestring,"time")?4:0;if(!bit||(mask&bit))goto fail;mask|=bit;}
    const cJSON *assets=cJSON_GetObjectItemCaseSensitive(v,"assets");if(!cJSON_IsArray(assets)||cJSON_GetArraySize(assets)>PR_ASSETS)goto fail;
    static const char *const akeys[]={"id","width","height","format","sha256","data_b64"};size_t total=0;
    for(const cJSON *a=assets->child;a;a=a->next) {
        int w,h;if(!fields(a,akeys,6)||!identifier(str(a,"id"))||!integer(a,"width",1,PR_WIDTH,&w)||!integer(a,"height",1,PR_HEIGHT,&h)||!eq(a,"format","rgba8888"))goto fail;
        const char *id=str(a,"id"),*encoded=str(a,"data_b64"),*hash=str(a,"sha256");size_t n=(size_t)w*h*4;
        if(n>PR_ASSET_BYTES-total||!encoded||strlen(encoded)!=4*((n+2)/3)||!hash||strlen(hash)!=64)goto fail;
        for(size_t j=0;j<p->program.asset_count;j++)if(!strcmp(id,p->assets[j].id))goto fail;
        uint8_t *raw=malloc(n);if(!raw)goto fail;size_t written=0;
        if(mbedtls_base64_decode(raw,n,&written,(const unsigned char *)encoded,strlen(encoded))||written!=n){free(raw);goto fail;}
        size_t canonical_size=4*((n+2)/3)+1;unsigned char *canonical=malloc(canonical_size);if(!canonical){free(raw);goto fail;}
        int code=mbedtls_base64_encode(canonical,canonical_size,&written,raw,n);bool matches=!code&&written==strlen(encoded)&&!memcmp(canonical,encoded,written);free(canonical);
        char actual[65];pr_sha256(raw,n,actual);if(!matches||strcmp(hash,actual)){free(raw);goto fail;}
        p->assets[p->program.asset_count++]=(pr_asset){id,(unsigned)w,(unsigned)h,raw,n};total+=n;
    }
    strcpy(p->app_id,str(v,"app_id"));strcpy(p->name,name);p->version=version;
    p->program.source=source;p->program.source_size=strlen(source);p->program.assets=p->assets;if(error)*error=NULL;return true;
fail:pr_package_free(p);return false;
}
