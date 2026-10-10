/* Real QuickJS with a deterministic monotonic clock; no host timing guesses. */
#define PR_TEST_CLOCK 1
#include "program_runtime.c"
#include <stdio.h>

static pr_startup *observed;
static const char *last_stage;
static unsigned stage_calls;
static int64_t fake_now, setup_delay, compile_delay, evaluate_delay;

int64_t pr_test_time_us(void) {
    const char *stage=observed?observed->stage:"callback";
    if(!last_stage||strcmp(last_stage,stage)){last_stage=stage;stage_calls=0;}
    if(++stage_calls==2)fake_now+=!strcmp(stage,"setup")?setup_delay:
        !strcmp(stage,"compile")?compile_delay:!strcmp(stage,"evaluate")?evaluate_delay:0;
    return fake_now;
}
static pr_runtime *sample(const char *source,pr_startup *startup,const char **error) {
    observed=startup;last_stage=NULL;stage_calls=0;fake_now=0;
    pr_program program={source,strlen(source),NULL,0};
    return pr_create_observed(&program,(pr_clock){0},1,error,NULL,startup);
}
int main(void) {
    pr_startup startup;const char *error=NULL;
    setup_delay=60000;compile_delay=40000;evaluate_delay=20000;
    pr_runtime *r=sample("let n=0;for(let i=0;i<1000;i++)n+=i;if(n!==499500)throw Error('calculation');",&startup,&error);
    assert(r&&!error&&!strcmp(startup.stage,"ready"));
    assert(startup.setup_us==60000&&startup.compile_us==40000&&startup.evaluate_us==20000);
    pr_destroy(r);
    /* Measured target compilation took57ms; it must not consume app execution. */
    setup_delay=0;compile_delay=57000;evaluate_delay=20000;
    r=sample("let n=0;for(let i=0;i<1000;i++)n+=i;",&startup,&error);
    assert(r&&startup.compile_us==57000&&startup.evaluate_us==20000);pr_destroy(r);
    compile_delay=249999;evaluate_delay=0;
    r=sample("let n=1;",&startup,&error);assert(r);pr_destroy(r);
    /* Reject exactly at the compiler's separate250ms boundary and never evaluate. */
    setup_delay=0;compile_delay=250000;evaluate_delay=0;
    r=sample("while(true){}",&startup,&error);
    assert(!r&&!strcmp(error,"execution_budget")&&!strcmp(startup.stage,"compile"));
    assert(startup.compile_us==250000&&!startup.evaluate_us&&!startup.evaluate_interrupts);
    compile_delay=0;evaluate_delay=60000;
    r=sample("while(true){}",&startup,&error);
    assert(!r&&!strcmp(error,"execution_budget")&&!strcmp(startup.stage,"evaluate"));
    assert(startup.evaluate_us==60000&&startup.evaluate_interrupts>0);
    /* No wall-clock advance: the independent interrupt-count cap still stops JS. */
    evaluate_delay=0;r=sample("while(true){}",&startup,&error);
    assert(!r&&!strcmp(error,"execution_budget")&&startup.evaluate_interrupts==1001);
    r=sample("app.onTick(()=>{while(true){}});",&startup,&error);assert(r);
    observed=NULL;last_stage=NULL;stage_calls=0;pr_set_activation(r,1);
    assert(!pr_dispatch(r,(pr_event){1,1,PR_TICK,0,0},(pr_clock){1,0,PR_WALL_UNAVAILABLE}));
    assert(!strcmp(pr_get_metrics(r).fault,"execution_budget")&&r->interrupt_calls==1001);
    pr_destroy(r);
    puts("{\"status\":\"startup_budget_tests_passed\",\"real_engine\":true,\"clock\":\"deterministic\",\"physical_execution\":false}");
    return 0;
}
