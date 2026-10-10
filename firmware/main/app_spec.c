#include "app_spec.h"
#include "cJSON.h"
#include <limits.h>
#include <math.h>
#include <stdlib.h>
#include <string.h>

static const cJSON *get(const cJSON *o, const char *key) {
    return cJSON_GetObjectItemCaseSensitive(o, key);
}
static const char *str(const cJSON *o, const char *key) {
    return cJSON_GetStringValue(get(o, key));
}
static bool equal(const char *a, const char *b) { return a && !strcmp(a, b); }
static bool integer(const cJSON *n, int64_t low, int64_t high) {
    return cJSON_IsNumber(n) && isfinite(n->valuedouble) &&
        n->valuedouble >= low && n->valuedouble <= high &&
        floor(n->valuedouble) == n->valuedouble;
}
static bool identifier(const char *s) {
    if (!s || s[0] < 'a' || s[0] > 'z' || strlen(s) >= AS_ID) return false;
    for (++s; *s; ++s)
        if (!(*s >= 'a' && *s <= 'z') && !(*s >= '0' && *s <= '9') &&
            *s != '_' && *s != '-') return false;
    return true;
}
static bool text_ok(const char *s, size_t maximum) {
    if (!s || !*s || strlen(s) > maximum) return false;
    for (; *s; ++s) if ((unsigned char)*s < 32 || (unsigned char)*s > 126) return false;
    return true;
}
static bool word_in(const char *words, const char *key) {
    if (!key) return false;
    size_t n = strlen(key);
    while (*words) {
        const char *end = strchr(words, ' ');
        size_t length = end ? (size_t)(end - words) : strlen(words);
        if (length == n && !memcmp(words, key, n)) return true;
        if (!end) break;
        words = end + 1;
    }
    return false;
}
static bool object(const cJSON *o, const char *required, const char *optional) {
    if (!cJSON_IsObject(o)) return false;
    for (const cJSON *p = o->child; p; p = p->next)
        if (!word_in(required, p->string) && !word_in(optional, p->string)) return false;
    while (*required) {
        const char *end = strchr(required, ' ');
        size_t length = end ? (size_t)(end - required) : strlen(required);
        char key[64];
        if (length >= sizeof(key)) return false;
        memcpy(key, required, length); key[length] = 0;
        if (!get(o, key)) return false;
        if (!end) break;
        required = end + 1;
    }
    return true;
}
static bool array(const cJSON *a, int low, int high) {
    return cJSON_IsArray(a) && cJSON_GetArraySize(a) >= low && cJSON_GetArraySize(a) <= high;
}
static bool tree_ok(const cJSON *n) {
    if (!n) return false;
    for (const cJSON *p = n->child; p; p = p->next) {
        if (cJSON_IsObject(n))
            for (const cJSON *q = p->next; q; q = q->next)
                if (!strcmp(p->string, q->string)) return false;
        if (!tree_ok(p)) return false;
    }
    return true;
}
static bool space(unsigned char c) { return c == ' ' || c == '\t' || c == '\r' || c == '\n'; }
static bool preflight(const char *raw, size_t length) {
    int depth = 0;
    bool quoted = false;
    for (size_t i = 0; i < length; ++i) {
        unsigned char c = (unsigned char)raw[i];
        if (c >= 128 || c == 0) return false;
        if (quoted) {
            if (c < 32) return false;
            if (c == '"') quoted = false;
            else if (c == '\\') {
                if (++i >= length) return false;
                /* cJSON strings use NUL termination; forbid embedded NUL escapes. */
                if (raw[i] == 'u' && i + 4 < length && !memcmp(raw + i + 1, "0000", 4)) return false;
            }
        } else if (c == '"') quoted = true;
        else if (c == '{' || c == '[') { if (++depth > 12) return false; }
        else if (c == '}' || c == ']') { if (--depth < 0) return false; }
        else if (c == '-' || (c >= '0' && c <= '9')) {
            if (c == '-' && (++i >= length || raw[i] < '0' || raw[i] > '9')) return false;
            if (raw[i] == '0') ++i;
            else while (i < length && raw[i] >= '0' && raw[i] <= '9') ++i;
            if (i < length && !space(raw[i]) && raw[i] != ',' && raw[i] != ']' && raw[i] != '}') return false;
            --i;
        } else if (c < 32 && !space(c)) return false;
    }
    return !quoted && depth == 0;
}
int as_find_state(const as_app *a, const char *id) {
    for (int i = 0; id && i < a->state_count; ++i) if (equal(id, a->state[i].id)) return i;
    return -1;
}
int as_find_widget(const as_app *a, const char *id) {
    for (int i = 0; id && i < a->widget_count; ++i) if (equal(id, a->widgets[i].id)) return i;
    return -1;
}
static int screen_id(const as_app *a, const char *id) {
    for (int i = 0; id && i < a->screen_count; ++i) if (equal(id, a->screens[i].id)) return i;
    return -1;
}
int as_text_height(const char *text, int available) {
    int columns = available / 16;
    return *text ? ((int)strlen(text) + columns - 1) / columns * 24 : 0;
}
int as_widget_height(const as_widget *w) {
    int available = 288 - (w->type == AS_LABEL ? 0 : 16) - (w->type == AS_TOGGLE ? 32 : 0);
    int height = as_text_height(w->text, available);
    if (w->type == AS_COUNTER || w->type == AS_TIMER) height += 24;
    if (w->type != AS_LABEL) { height += 16; if (height < 48) height = 48; }
    return height;
}
static bool parse_action(const cJSON *n, as_app *a, as_action *out, bool completion) {
    const char *type = str(n, "type");
    out->target = -1;
    if (equal(type, "navigate")) {
        if (!object(n, "type screen_id", "")) return false;
        out->type = AS_NAVIGATE; out->target = screen_id(a, str(n, "screen_id"));
    } else if (equal(type, "timer_start") || equal(type, "timer_pause") || equal(type, "timer_reset")) {
        if (completion || !object(n, "type widget_id", "")) return false;
        int widget = as_find_widget(a, str(n, "widget_id"));
        if (widget < 0 || a->widgets[widget].type != AS_TIMER) return false;
        out->target = a->widgets[widget].timer;
        out->type = equal(type, "timer_start") ? AS_START : equal(type, "timer_pause") ? AS_PAUSE : AS_RESET;
    } else {
        out->target = as_find_state(a, str(n, "state_key"));
        if (out->target < 0) return false;
        bool boolean = a->state[out->target].boolean;
        if (equal(type, "set")) {
            const cJSON *value = get(n, "value");
            if (!object(n, "type state_key value", "") ||
                (boolean ? !cJSON_IsBool(value) : !integer(value, INT32_MIN, INT32_MAX))) return false;
            out->type = AS_SET; out->value = boolean ? cJSON_IsTrue(value) : (int32_t)value->valuedouble;
        } else if (equal(type, "increment")) {
            if (boolean || !object(n, "type state_key amount", "") || !integer(get(n, "amount"), INT32_MIN, INT32_MAX)) return false;
            out->type = AS_INCREMENT; out->value = (int32_t)get(n, "amount")->valuedouble;
        } else if (equal(type, "toggle")) {
            if (!boolean || !object(n, "type state_key", "")) return false;
            out->type = AS_FLIP;
        } else return false;
    }
    return out->target >= 0;
}

bool as_parse(const char *bytes, size_t size, as_app *a, const char **error) {
    if (error) *error = "invalid_json";
    if (!bytes || !a || !size || size > AS_MAX_BYTES || !preflight(bytes, size)) return false;
    const char *end = NULL;
    cJSON *root = cJSON_ParseWithLengthOpts(bytes, size, &end, false);
    if (!root) return false;
    while (end < bytes + size && space((unsigned char)*end)) ++end;
    if (end != bytes + size || !tree_ok(root)) { cJSON_Delete(root); return false; }
    memset(a, 0, sizeof(*a));
    bool ok = false;
    const cJSON *widget_nodes[AS_MAX_WIDGETS] = {0};
    if (error) *error = "invalid_schema";
    if (!object(root, "schema_version app_id version name target theme initial_screen state screens", "") ||
        !integer(get(root, "schema_version"), 1, 1) || !integer(get(root, "version"), 1, INT32_MAX) ||
        !identifier(str(root, "app_id")) || !text_ok(str(root, "name"), 48)) goto done;
    strcpy(a->app_id, str(root, "app_id")); strcpy(a->name, str(root, "name"));
    a->version = (int32_t)get(root, "version")->valuedouble;
    const cJSON *target = get(root, "target"), *theme = get(root, "theme");
    if (!object(target, "width height orientation", "") || !integer(get(target,"width"),320,320) ||
        !integer(get(target,"height"),480,480) || !equal(str(target,"orientation"),"portrait") ||
        !object(theme,"palette font_size","") || !equal(str(theme,"font_size"),"medium") ||
        (!equal(str(theme,"palette"),"dark_green") && !equal(str(theme,"palette"),"light_blue"))) goto done;
    a->dark = equal(str(theme,"palette"),"dark_green");
    const cJSON *states = get(root, "state"), *screens = get(root, "screens");
    if (!cJSON_IsObject(states) || cJSON_GetArraySize(states) > AS_MAX_STATE || !array(screens,1,AS_MAX_SCREENS)) goto done;
    for (const cJSON *p = states->child; p; p = p->next) {
        if (!identifier(p->string) || (!cJSON_IsBool(p) && !integer(p,INT32_MIN,INT32_MAX))) goto done;
        as_state_def *s = &a->state[a->state_count++];
        strcpy(s->id,p->string); s->boolean = cJSON_IsBool(p);
        s->initial = s->boolean ? cJSON_IsTrue(p) : (int32_t)p->valuedouble;
    }
    for (const cJSON *s = screens->child; s; s = s->next) {
        if (!object(s,"id title widgets","") || !identifier(str(s,"id")) ||
            screen_id(a,str(s,"id")) >= 0 || !text_ok(str(s,"title"),120) || !array(get(s,"widgets"),0,8)) goto done;
        int screen = a->screen_count++;
        as_screen *sd = &a->screens[screen];
        strcpy(sd->id,str(s,"id")); strcpy(sd->title,str(s,"title")); sd->first = a->widget_count;
        for (const cJSON *w = get(s,"widgets")->child; w; w = w->next) {
            if (a->widget_count == AS_MAX_WIDGETS || !identifier(str(w,"id")) || as_find_widget(a,str(w,"id")) >= 0) goto done;
            as_widget *wd = &a->widgets[a->widget_count];
            widget_nodes[a->widget_count++] = w; sd->count++;
            strcpy(wd->id,str(w,"id")); wd->screen = screen; wd->state = wd->timer = -1;
            const char *kind = str(w,"type"), *label = str(w,"text");
            if (get(w,"text")) { if (!text_ok(label,120)) goto done; strcpy(wd->text,label); }
            if (equal(kind,"label")) {
                if (!object(w,"id type text","")) goto done;
                wd->type = AS_LABEL;
            } else if (equal(kind,"button")) {
                if (!object(w,"id type text on_press","")) goto done;
                wd->type = AS_BUTTON;
            } else if (equal(kind,"counter") || equal(kind,"toggle")) {
                bool toggle = equal(kind,"toggle");
                if (!object(w,toggle ? "id type text state_key" : "id type state_key",toggle ? "" : "text")) goto done;
                wd->state = as_find_state(a,str(w,"state_key"));
                if (wd->state < 0 || a->state[wd->state].boolean != toggle) goto done;
                wd->type = toggle ? AS_TOGGLE : AS_COUNTER;
            } else if (equal(kind,"timer")) {
                if (!object(w,"id type duration_seconds on_complete","text") || a->timer_count == AS_MAX_TIMERS || !integer(get(w,"duration_seconds"),1,3600)) goto done;
                wd->type = AS_TIMER; wd->timer = a->timer_count;
                a->timer_widgets[a->timer_count++] = a->widget_count - 1;
                wd->duration = (int)get(w,"duration_seconds")->valuedouble;
            } else goto done;
        }
    }
    a->initial_screen = screen_id(a,str(root,"initial_screen"));
    if (a->initial_screen < 0) goto done;
    for (int i = 0; i < a->widget_count; ++i) {
        as_widget *w = &a->widgets[i];
        if (w->type != AS_BUTTON && w->type != AS_TIMER) continue;
        const cJSON *actions = get(widget_nodes[i],w->type == AS_BUTTON ? "on_press" : "on_complete");
        if (!array(actions,0,AS_MAX_ACTIONS)) goto done;
        for (const cJSON *action = actions->child; action; action = action->next)
            if (!parse_action(action,a,&w->actions[w->action_count++],w->type == AS_TIMER)) goto done;
    }
    if (error) *error = "layout";
    for (int i = 0; i < a->screen_count; ++i) {
        as_screen *s = &a->screens[i];
        int height = 32 + as_text_height(s->title,288);
        for (int j = s->first; j < s->first + s->count; ++j) height += 8 + as_widget_height(&a->widgets[j]);
        if (height > 432) goto done;
    }
    if (error) *error = "unreachable_screen";
    unsigned reachable = 1u << a->initial_screen;
    for (int pass = 0; pass < a->screen_count; ++pass)
        for (int i = 0; i < a->widget_count; ++i) {
            const as_widget *w = &a->widgets[i];
            if (w->type != AS_BUTTON || !(reachable & (1u << w->screen))) continue;
            for (int j = 0; j < w->action_count; ++j) {
                const as_action *action = &w->actions[j];
                if (action->type == AS_NAVIGATE) reachable |= 1u << action->target;
                if (action->type == AS_START) {
                    const as_widget *timer = &a->widgets[a->timer_widgets[action->target]];
                    for (int k = 0; k < timer->action_count; ++k)
                        if (timer->actions[k].type == AS_NAVIGATE) reachable |= 1u << timer->actions[k].target;
                }
            }
        }
    if (reachable != (1u << a->screen_count) - 1u) goto done;
    ok = true;
    if (error) *error = NULL;
done:
    cJSON_Delete(root);
    return ok;
}

void as_install(as_runtime *r, const as_app *a, int64_t now, uint64_t activation) {
    memset(r,0,sizeof(*r)); r->app = a; r->screen = a->initial_screen;
    r->now = now; r->activation = activation; r->entry = 1;
    for (int i = 0; i < a->state_count; ++i) r->state[i] = a->state[i].initial;
    for (int i = 0; i < a->timer_count; ++i) r->timers[i].remaining = a->widgets[a->timer_widgets[i]].duration * 1000LL;
}
int64_t as_remaining(const as_runtime *r, int timer) {
    const as_timer *t = &r->timers[timer];
    int64_t value = t->status == AS_RUNNING && !r->in_shell ? t->deadline - r->now : t->remaining;
    return value > 0 ? value : 0;
}
static bool actions(as_runtime *r, const as_action *list, int count) {
    as_runtime next = *r;
    for (int i = 0; i < count; ++i) {
        const as_action *a = &list[i];
        if (a->type == AS_NAVIGATE) { next.screen = a->target; ++next.entry; }
        else if (a->type == AS_SET) next.state[a->target] = a->value;
        else if (a->type == AS_INCREMENT) {
            int64_t value = (int64_t)next.state[a->target] + a->value;
            if (value < INT32_MIN || value > INT32_MAX) { ++r->rejected_events; return false; }
            next.state[a->target] = (int32_t)value;
        } else if (a->type == AS_FLIP) next.state[a->target] = !next.state[a->target];
        else {
            as_timer *t = &next.timers[a->target];
            if (a->type == AS_RESET) {
                t->status = AS_IDLE; t->deadline = 0;
                t->remaining = r->app->widgets[r->app->timer_widgets[a->target]].duration * 1000LL;
            } else if (a->type == AS_START && (t->status == AS_IDLE || t->status == AS_PAUSED)) {
                t->status = AS_RUNNING; t->deadline = r->now + t->remaining;
            } else if (a->type == AS_PAUSE && t->status == AS_RUNNING) {
                t->remaining = t->deadline > r->now ? t->deadline - r->now : 0;
                t->deadline = 0; t->status = AS_PAUSED;
            }
        }
    }
    *r = next;
    return true;
}
void as_advance(as_runtime *r, int64_t now) {
    if (now < r->now) return;
    r->now = now;
    if (r->in_shell) return;
    int due[AS_MAX_TIMERS], count = 0;
    for (int i = 0; i < r->app->timer_count; ++i)
        if (r->timers[i].status == AS_RUNNING && r->timers[i].deadline <= now) due[count++] = i;
    if (count == 2) {
        int a = due[0], b = due[1];
        if (r->timers[a].deadline > r->timers[b].deadline ||
            (r->timers[a].deadline == r->timers[b].deadline &&
             strcmp(r->app->widgets[r->app->timer_widgets[a]].id,r->app->widgets[r->app->timer_widgets[b]].id) > 0)) {
            due[0] = b; due[1] = a;
        }
    }
    for (int i = 0; i < count; ++i) {
        int timer = due[i];
        r->timers[timer] = (as_timer){.status=AS_COMPLETED};
        const as_widget *w = &r->app->widgets[r->app->timer_widgets[timer]];
        actions(r,w->actions,w->action_count);
    }
}
bool as_press(as_runtime *r, int widget, int64_t now, as_event_token token) {
    if (now < r->now) return false;
    as_advance(r,now);
    if (r->in_shell || token.activation != r->activation || token.entry != r->entry ||
        widget < 0 || widget >= r->app->widget_count || r->app->widgets[widget].screen != r->screen) return false;
    const as_widget *w = &r->app->widgets[widget];
    if (w->type == AS_BUTTON) return actions(r,w->actions,w->action_count);
    if (w->type == AS_TOGGLE) { as_action a = {.type=AS_FLIP,.target=w->state}; return actions(r,&a,1); }
    return false;
}
void as_shell(as_runtime *r, bool enter, int64_t now) {
    if (now < r->now) return;
    if (enter) {
        as_advance(r,now);
        if (r->in_shell) return;
        for (int i = 0; i < r->app->timer_count; ++i)
            if (r->timers[i].status == AS_RUNNING) {
                r->timers[i].remaining = as_remaining(r,i); r->timers[i].deadline = 0;
            }
        r->in_shell = true;
    } else {
        r->now = now;
        if (!r->in_shell) { as_advance(r,now); return; }
        for (int i = 0; i < r->app->timer_count; ++i)
            if (r->timers[i].status == AS_RUNNING) r->timers[i].deadline = now + r->timers[i].remaining;
        r->in_shell = false;
    }
    ++r->entry;
}
