#include "app_spec.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static as_app app;
static char bytes[AS_MAX_BYTES+1];
static bool load(const char *path) {
    FILE *file = fopen(path,"rb");
    if (!file) return false;
    size_t size = fread(bytes,1,sizeof(bytes),file); fclose(file);
    const char *error;
    return as_parse(bytes,size,&app,&error);
}
static as_event_token token(const as_runtime *r) { return (as_event_token){r->activation,r->entry}; }
static void press(as_runtime *r, const char *id, int64_t now) {
    assert(as_press(r,as_find_widget(&app,id),now,token(r)));
}
int main(int argc, char **argv) {
    if (argc == 3 && !strcmp(argv[1],"--validate")) {
        bool valid = load(argv[2]);
        puts(valid ? "valid" : "invalid"); return valid ? 0 : 1;
    }
    assert(argc == 3 && load(argv[1]));
    as_runtime r;
    as_install(&r,&app,0,1);
    int score = as_find_state(&app,"score");
    press(&r,"start",100);
    assert(!strcmp(app.screens[r.screen].id,"play"));
    assert(as_remaining(&r,0) == 10000);
    press(&r,"tap",101); press(&r,"tap",200); press(&r,"tap",10099);
    as_event_token old = token(&r);
    assert(!as_press(&r,as_find_widget(&app,"tap"),10100,old));
    assert(r.state[score] == 3 && !strcmp(app.screens[r.screen].id,"result"));
    press(&r,"again",11000);
    assert(r.state[score] == 0 && as_remaining(&r,0) == 10000);
    assert(!as_press(&r,as_find_widget(&app,"tap"),11001,old));
    as_shell(&r,true,12000); as_advance(&r,20000);
    assert(as_remaining(&r,0) == 9000);
    as_shell(&r,false,21000); as_advance(&r,29999);
    assert(!strcmp(app.screens[r.screen].id,"play"));
    as_advance(&r,30000);
    assert(!strcmp(app.screens[r.screen].id,"result"));
    press(&r,"again",31000);
    int start = as_find_widget(&app,"again");
    int tap = as_find_widget(&app,"tap");
    app.widgets[tap].action_count = 2;
    app.widgets[tap].actions[0] = (as_action){.type=AS_NAVIGATE,.target=0};
    app.widgets[tap].actions[1] = (as_action){.type=AS_INCREMENT,.target=score,.value=1};
    r.state[score] = INT32_MAX;
    uint64_t entry = r.entry;
    assert(!as_press(&r,tap,31001,token(&r)));
    assert(r.state[score] == INT32_MAX && r.entry == entry && r.screen == 1);
    (void)start;
    assert(load(argv[2]));
    as_install(&r,&app,0,2);
    press(&r,"begin",0); as_advance(&r,1000); press(&r,"pause",1000);
    assert(as_remaining(&r,0) == 4000);
    as_advance(&r,10000); press(&r,"begin",10000); as_advance(&r,14000);
    assert(r.state[as_find_state(&app,"done")] == 1);
    press(&r,"done_toggle",14001);
    assert(r.state[as_find_state(&app,"done")] == 0);
    press(&r,"restart",14002);
    assert(r.timers[0].status == AS_IDLE && as_remaining(&r,0) == 5000);
    puts("PASS: native tap/timer traces, deadline, replay, stale event, shell suspension, atomic overflow, toggle");
    return 0;
}
