#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <assert.h>
#define pdTRUE 1
#define pdFALSE 0
#define pdPASS 1
#define portMAX_DELAY UINT32_MAX
#define pdMS_TO_TICKS(x) (x)
#define MALLOC_CAP_INTERNAL 1
#define MALLOC_CAP_SPIRAM 2
#define MALLOC_CAP_8BIT 4
typedef struct host_queue { size_t count, capacity, size, head; unsigned char data[]; } *QueueHandle_t;
typedef void *SemaphoreHandle_t;
typedef void *TaskHandle_t;
static int64_t host_us=1000000;
static bool host_display_locked;
static size_t host_internal_free=8*1024*1024, host_external_free=16*1024*1024;
static unsigned host_stack_size;
static inline SemaphoreHandle_t xSemaphoreCreateMutex(void){return (void *)1;}
static inline int xSemaphoreTake(SemaphoreHandle_t s,unsigned timeout){(void)s;(void)timeout;return pdTRUE;}
static inline void xSemaphoreGive(SemaphoreHandle_t s){(void)s;}
static inline QueueHandle_t xQueueCreate(size_t capacity,size_t size){
    QueueHandle_t q=calloc(1,sizeof(*q)+capacity*size);if(q){q->capacity=capacity;q->size=size;}return q;
}
static inline int xQueueSend(QueueHandle_t q,const void *value,unsigned timeout){
    (void)timeout;if(q->count==q->capacity)return pdFALSE;
    memcpy(q->data+((q->head+q->count)%q->capacity)*q->size,value,q->size);++q->count;return pdTRUE;
}
static inline int xQueueReceive(QueueHandle_t q,void *value,unsigned timeout){
    (void)timeout;if(!q->count)return pdFALSE;memcpy(value,q->data+q->head*q->size,q->size);
    q->head=(q->head+1)%q->capacity;--q->count;return pdTRUE;
}
static inline void xQueueReset(QueueHandle_t q){q->count=q->head=0;}
static inline void vQueueDelete(QueueHandle_t q){free(q);}
static inline void vSemaphoreDelete(SemaphoreHandle_t s){(void)s;}
static inline int xQueueOverwrite(QueueHandle_t q,const void *value){assert(q->capacity==1);xQueueReset(q);return xQueueSend(q,value,0);}
static inline int xTaskCreate(void (*f)(void *),const char *name,unsigned stack,void *arg,int priority,TaskHandle_t *task){
    (void)f;(void)name;(void)arg;(void)priority;host_stack_size=stack;*task=(void *)1;return pdPASS;
}
static inline unsigned uxTaskGetStackHighWaterMark(TaskHandle_t task){(void)task;return 32768;}
static inline void vTaskDelay(unsigned ticks){host_us+=(int64_t)ticks*1000;}
static inline int64_t esp_timer_get_time(void){return host_us;}
static inline uint32_t esp_random(void){return 12345;}
static inline size_t heap_caps_get_free_size(unsigned caps){return caps&MALLOC_CAP_SPIRAM?host_external_free:host_internal_free;}
static inline size_t heap_caps_get_largest_free_block(unsigned caps){return heap_caps_get_free_size(caps);}
static unsigned host_lock_depth;
static inline bool bsp_display_lock(uint32_t timeout){(void)timeout;++host_lock_depth;host_display_locked=true;return true;}
static inline void bsp_display_unlock(void){assert(host_lock_depth);if(!--host_lock_depth)host_display_locked=false;}
