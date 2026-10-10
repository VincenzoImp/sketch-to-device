"""Execute the real browser controller against synthetic transport responses."""

from pathlib import Path
import shutil
import subprocess
import unittest


class CompanionRecoveryTests(unittest.TestCase):
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
 const c={URLSearchParams,location:{hash:'',pathname:'/'},history:{replaceState(){}},
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
