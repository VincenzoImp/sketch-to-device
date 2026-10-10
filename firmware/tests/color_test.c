#include "app_spec.h"
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>

int main(int argc, char **argv) {
    /* Known contrasting colors and the neighboring grayscale crossover. */
    const uint32_t backgrounds[]={0x000000,0xFFFFFF,0xFF69B4,0xFF0000,0x00FF00,
                                  0x0000FF,0x164EAD,0x80FF80,0x757575,0x767676};
    const uint32_t foregrounds[]={0xFFFFFF,0x000000,0x000000,0x000000,0x000000,
                                  0xFFFFFF,0xFFFFFF,0x000000,0xFFFFFF,0x000000};
    for (size_t i=0;i<sizeof(backgrounds)/sizeof(backgrounds[0]);++i)
        assert(as_color_foreground(backgrounds[i])==foregrounds[i]);
    assert(argc==2);
    FILE *file=fopen(argv[1],"rb");assert(file);
    char bytes[AS_MAX_BYTES+1];size_t size=fread(bytes,1,sizeof(bytes),file);fclose(file);
    as_app app;const char *error;assert(as_parse(bytes,size,&app,&error));
    assert(app.screen_count==3 && app.widget_count==3 && app.state_count==0);
    const uint32_t cycle[]={0xFF69B4,0x164EAD,0x80FF80};
    as_runtime runtime;as_install(&runtime,&app,0,1);
    for (int i=0;i<12;++i) {
        assert(runtime.screen==i%3);
        int index=app.screens[runtime.screen].first;
        const as_widget *widget=&app.widgets[index];
        assert(widget->type==AS_BUTTON && widget->has_background_color);
        assert(widget->background_color==cycle[i%3]);
        as_event_token previous={runtime.activation,runtime.entry};
        assert(as_press(&runtime,index,i+1,previous));
        assert(runtime.screen==(i+1)%3);
        assert(!as_press(&runtime,index,i+1,previous));
    }
    as_shell(&runtime,true,20);
    assert(!as_press(&runtime,0,21,(as_event_token){runtime.activation,runtime.entry}));
    as_shell(&runtime,false,22);
    assert(runtime.screen==0 && app.widgets[0].background_color==cycle[0]);
    puts("PASS: foreground contrast, three-screen color cycle, stale clicks and shell isolation");
    return 0;
}
