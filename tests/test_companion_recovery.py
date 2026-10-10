"""Execute the real browser controller against synthetic transport responses."""

from pathlib import Path
import shutil
import subprocess
import unittest


class CompanionRecoveryTests(unittest.TestCase):
    def run_controller(self, body):
        node = shutil.which("node") or "/opt/homebrew/bin/node"
        if not Path(node).is_file():
            self.skipTest("Node is required for the actual controller check")
        harness = r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(process.argv[1],'utf8');
function boot(initial={}) {
 const values=new Map(Object.entries(initial)), elements=new Map(), timers=new Map();
 let interval, serial=0, transport=async()=>({ok:true,json:async()=>({})});
 function element(){return {children:[],value:'',classList:{toggle(){}},addEventListener(name,fn){this[name]=fn},replaceChildren(){},textContent:'',hidden:true};}
 const c={URLSearchParams,AbortController,crypto:require('crypto').webcrypto,location:{hash:'',pathname:'/'},history:{replaceState(){}},
 sessionStorage:{getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)},
 document:{querySelector(s){if(!elements.has(s))elements.set(s,element());return elements.get(s)},createElement:element},
 setInterval(fn){interval=fn},setTimeout(fn,ms){if(![15000,120000].includes(ms))return setTimeout(fn,ms);let id=++serial;timers.set(id,fn);return id},
 clearTimeout(id){timers.delete(id)},fetch:(...args)=>transport(...args)};
 for(const match of source.matchAll(/\$\('([^']+)'\)/g))c.document.querySelector(match[1]);
 c.window=c;vm.createContext(c);vm.runInContext(source,c);
 return {c,values,e:elements,interval:()=>interval(),run:code=>vm.runInContext(code,c),
 transport(fn){transport=fn},expire(){for(const fn of [...timers.values()])fn()},timers};
}
const tick=()=>new Promise(resolve=>setImmediate(resolve));
const response=(data,status=200)=>({ok:status>=200&&status<300,status,json:async()=>data});
(async()=>{
'''
        result = subprocess.run([node, "-e", harness + body + r'''
})().catch(error=>{console.error(error);process.exitCode=1});
''', str(Path(__file__).resolve().parents[1] / "companion/app.js")],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_definitively_missing_job_releases_resume_but_uncertain_errors_retain_it(self):
        self.run_controller(r'''
 const b=boot(); b.values.set('last-job','gone');
 for (const [status,code] of [[500,'service_error'],[401,'authentication_required'],[400,'invalid_operation'],[404,'route_not_found']]) {
  b.transport(async()=>response({error:code},status));await b.run('recover()');
  assert.equal(b.values.get('last-job'),'gone');assert.equal(b.run('working'),false);
 }
 b.transport(async()=>response({error:'job_not_found'},404));await b.run('recover()');
 assert(!b.values.has('last-job'));assert.equal(b.e.get('#generate').textContent,'Generate and install ↗');
 assert.match(b.e.get('#error').textContent,/start a new request/);
 b.e.get('#prompt').value='A fresh idea';let posts=0;
 b.transport(async(path,options)=>{
  if(path==='/api/generate'){posts++;assert.equal(JSON.parse(options.body).prompt,'A fresh idea');return response({job_id:'new'})}
  return response({stage:'active',device_online:true});
 });
 await b.e.get('#create-form').submit({preventDefault(){}});
 assert.equal(posts,1);assert.equal(b.values.get('active-job'),'new');
 // Only the identity whose lookup failed may be cleared.
 let release;b.values.set('last-job','old');b.transport(()=>new Promise(resolve=>{release=resolve}));
 const old=b.run("readJob('old','last-job')").catch(()=>{});b.values.set('last-job','newer');
 release(response({error:'job_not_found'},404));await old;assert.equal(b.values.get('last-job'),'newer');
''')

    def test_fetch_and_body_timeout_preserve_exact_pending_post_for_retry(self):
        self.run_controller(r'''
 const b=boot();const frozen=JSON.stringify({prompt:'Keep this exact idea',uploads:[],request_id:'same-request'});
 for(const phase of ['fetch','body']) {
  b.values.set('pending-request',frozen);let sent,aborted=false;
  b.transport(async(path,options)=>{
   assert.equal(path,'/api/generate');sent=options.body;
   const never=()=>new Promise((resolve,reject)=>options.signal.addEventListener('abort',()=>{aborted=true;reject(new Error('aborted'))},{once:true}));
   return phase==='fetch'?never():{ok:true,status:202,json:never};
  });
  const pending=b.run('recover()');await tick();b.expire();await pending;
  assert(aborted);assert.equal(sent,frozen);assert.equal(b.values.get('pending-request'),frozen);
  assert.equal(b.run('working'),false);assert.equal(b.timers.size,0);
  assert.match(b.e.get('#error').textContent,/stopped responding/);
 }
 b.transport(async(path,options)=>path==='/api/generate'?(assert.equal(options.body,frozen),response({job_id:'accepted'})):response({stage:'active',device_online:true}));
 await b.run('recover()');assert(!b.values.has('pending-request'));assert.equal(b.values.get('active-job'),'accepted');
 // Gateway timeouts and rate limiting do not establish rejection of a POST.
 for(const status of [408,429,504]){
  b.values.set('pending-request',frozen);b.transport(async()=>response({error:'service_error'},status));await b.run('recover()');
  assert.equal(b.values.get('pending-request'),frozen);
 }
 // Large uploads have a separate bounded transfer allowance.
 let uploadDelay;b.c.setTimeout=(fn,ms)=>{uploadDelay=ms;return 0};b.c.clearTimeout=()=>{};
 b.transport(async()=>response({upload_id:'ok'}));await b.run("request('/api/uploads',{method:'POST',body:'bytes'})");
 assert.equal(uploadDelay,120000);
''')

    def test_session_active_identity_is_separate_from_progress_and_offline_claims(self):
        self.run_controller(r'''
 const b=boot();b.run("token='workspace'");
 const active={deployment_id:'actual',manifest:{app_id:'penguin-tap',version:3,sha256:'f'.repeat(64)}};
 let session={device_online:true,generation_busy:false,active_app:active};
 b.transport(async()=>response(session));await b.run('connect()');
 assert.equal(b.e.get('#active-app').hidden,false);assert.equal(b.e.get('#active-app').textContent,'Last acknowledged app: penguin-tap · v3');
 assert.equal(b.e.get('#progress').hidden,true);
 b.run("progress('recovered','The previous app was restored.');showError('Keep this error')");
 session={...session,device_online:false};await b.interval();
 assert.equal(b.e.get('#progress-label').textContent,'APP RECOVERED');assert.equal(b.e.get('#error').textContent,'Keep this error');
 assert.match(b.e.get('#device-status').textContent,/waiting/);assert.match(b.e.get('#active-app').textContent,/Last acknowledged/);
 b.values.set('active-job','actual-job');b.transport(async()=>response({stage:'active',device_online:false,deployment:active}));await b.run('pollActive()');
 assert.equal(b.e.get('#progress-label').textContent,'INSTALLED · DEVICE OFFLINE');
 // A session response begun while idle must not alter a new request's progress.
 let release,calls=0;b.transport(()=>{calls++;return new Promise(resolve=>{release=resolve})});
 const late=b.interval();await tick();await b.interval();assert.equal(calls,1);
 b.run("setWorking(true);progress('generating','New idea')");release(response(session));await late;
 assert.equal(b.e.get('#progress-title').textContent,'Building your app');
 // A temporary backend restart must not demand another access token.
 b.run('setWorking(false)');b.transport(async()=>response({error:'service_error'},503));await b.run('connect()');
 assert.equal(b.e.get('#workspace').hidden,false);assert.equal(b.e.get('#connect').hidden,true);
 b.transport(async()=>response({...session,device_online:true}));b.values.delete('active-job');await b.interval();
 assert.equal(b.e.get('#workspace').hidden,false);assert.match(b.e.get('#device-status').textContent,/ready/);
 // Explicitly changing workspace must not replay another workspace's saved body.
 b.values.set('pending-request','private old body');b.values.set('last-job','old');
 b.e.get('#access-token').value='different';b.transport(async()=>response({device_online:false,active_app:null}));
 b.e.get('#connect-form').submit({preventDefault(){}});await tick();
 assert(!b.values.has('pending-request'));assert(!b.values.has('last-job'));assert(!b.values.has('active-job'));
''')

    def test_active_watch_survives_reload_and_late_recovery_without_blocking_new_work(self):
        node = shutil.which("node") or "/opt/homebrew/bin/node"
        if not Path(node).is_file():
            self.skipTest("Node is required for the actual controller check")
        script = r'''
const fs=require('fs'), vm=require('vm'), assert=require('assert');
const source=fs.readFileSync(process.argv[1],'utf8'), values=new Map();
let job={stage:'active',detail:'Running',device_online:true}, pending=null;
function boot(){
 const elements=new Map(); let interval;
 function element(){return {children:[],classList:{toggle(){}},addEventListener(){},replaceChildren(){},textContent:'',hidden:true};}
 const c={URLSearchParams,AbortController,location:{hash:'',pathname:'/'},history:{replaceState(){}},
 sessionStorage:{getItem:k=>values.get(k)||null,setItem:(k,v)=>values.set(k,v),removeItem:k=>values.delete(k)},
 document:{querySelector(s){if(!elements.has(s))elements.set(s,element());return elements.get(s)},createElement:element},
 setInterval(fn){interval=fn},setTimeout,clearTimeout,
 fetch:async path=>({ok:true,json:async()=>path==='/api/session'?{device_online:true}:pending?await pending:job})};
 c.window=c;vm.createContext(c);vm.runInContext(source,c);
 return {c,e:elements,interval:()=>interval()};
}
(async()=>{
 const first=boot();
 values.set('last-job','one');
 await vm.runInContext("watch('one')",first.c);
 assert.equal(values.get('active-job'),'one');assert(!values.has('last-job'));
 values.set('workspace-token','synthetic-token');
 const second=boot();await new Promise(r=>setImmediate(r));
 assert.equal(second.e.get('#progress-label').textContent,'RUNNING ON YOUR DEVICE');
 job={stage:'recovered',detail:'The previous app was restored.',device_online:true};
 await second.interval();
 assert.equal(second.e.get('#progress-label').textContent,'APP RECOVERED');
 assert(!values.has('active-job'));
 assert.equal(vm.runInContext('working',second.c),false);
 vm.runInContext('setWorking(false)',second.c);
 assert.equal(second.e.get('#generate').disabled,false);
 // An in-flight old-app response cannot replace new generation progress.
 values.set('active-job','old');let release;
 pending=new Promise(r=>{release=r});
 const late=vm.runInContext('pollActive()',second.c);
 vm.runInContext("setWorking(true);progress('generating','New request')",second.c);
 release(job);await late;
 assert.equal(second.e.get('#progress-title').textContent,'Building your app');
 console.log('active recovery controller checks passed');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
        result = subprocess.run([node, "-e", script, str(Path(__file__).resolve().parents[1] / "companion/app.js")],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("active recovery controller checks passed", result.stdout)


if __name__ == "__main__":
    unittest.main()
