#pragma once
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define AS_MAX_BYTES 65536
#define AS_MAX_SCREENS 6
#define AS_MAX_WIDGETS 32
#define AS_MAX_STATE 16
#define AS_MAX_TIMERS 2
#define AS_MAX_ACTIONS 4
#define AS_ID 49
#define AS_TEXT 121

typedef enum { AS_LABEL, AS_BUTTON, AS_COUNTER, AS_TOGGLE, AS_TIMER } as_widget_type;
typedef enum { AS_NAVIGATE, AS_SET, AS_INCREMENT, AS_FLIP, AS_START, AS_PAUSE, AS_RESET } as_action_type;
typedef enum { AS_IDLE, AS_RUNNING, AS_PAUSED, AS_COMPLETED } as_timer_status;
typedef struct { as_action_type type; int target; int32_t value; } as_action;
typedef struct { char id[AS_ID]; bool boolean; int32_t initial; } as_state_def;
typedef struct {
    char id[AS_ID], text[AS_TEXT];
    as_widget_type type;
    int screen, state, timer, duration, action_count;
    as_action actions[AS_MAX_ACTIONS];
} as_widget;
typedef struct { char id[AS_ID], title[AS_TEXT]; int first, count; } as_screen;
typedef struct {
    char app_id[AS_ID], name[AS_ID];
    int32_t version;
    bool dark;
    int initial_screen, state_count, screen_count, widget_count, timer_count;
    as_state_def state[AS_MAX_STATE];
    as_screen screens[AS_MAX_SCREENS];
    as_widget widgets[AS_MAX_WIDGETS];
    int timer_widgets[AS_MAX_TIMERS];
} as_app;
typedef struct { as_timer_status status; int64_t remaining, deadline; } as_timer;
typedef struct {
    const as_app *app;
    int32_t state[AS_MAX_STATE];
    as_timer timers[AS_MAX_TIMERS];
    int screen;
    int64_t now;
    uint64_t activation, entry;
    unsigned rejected_events;
    bool in_shell;
} as_runtime;
typedef struct { uint64_t activation, entry; } as_event_token;

bool as_parse(const char *bytes, size_t size, as_app *out, const char **error);
int as_find_widget(const as_app *app, const char *id);
int as_find_state(const as_app *app, const char *id);
int as_widget_height(const as_widget *widget);
int as_text_height(const char *text, int available);
void as_install(as_runtime *rt, const as_app *app, int64_t now, uint64_t activation);
void as_advance(as_runtime *rt, int64_t now);
bool as_press(as_runtime *rt, int widget, int64_t now, as_event_token token);
void as_shell(as_runtime *rt, bool enter, int64_t now);
int64_t as_remaining(const as_runtime *rt, int timer);
