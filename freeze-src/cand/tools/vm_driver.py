"""One existing-VM qualification job, with exact local gate and bounded handoff."""
import datetime,hashlib,json,os,signal,socket,subprocess,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
UTC=datetime.timezone.utc
LATEST_START=datetime.datetime(2026,10,12,6,0,0,tzinfo=UTC).timestamp()
DEADLINE=datetime.datetime(2026,10,12,18,0,0,tzinfo=UTC).timestamp()
def utc():return datetime.datetime.now(UTC).isoformat()
def save(name,data):
 p=ROOT/name;tmp=p.with_name(p.name+'.next');tmp.write_text(json.dumps(data,indent=2));tmp.rename(p)
def memkb():return int(Path('/proc/meminfo').read_text().split('MemAvailable:')[1].split()[0])
def parseutc(s):return datetime.datetime.fromisoformat(s.replace('Z','+00:00')).timestamp()
def progress():
 p=ROOT/'vm-10m.log'
 if not p.exists():return []
 with p.open('rb') as f:
  f.seek(max(0,p.stat().st_size-4096));return f.read().decode('utf8',errors='replace').splitlines()[-8:]
def stop(proc):
 if proc.poll() is None:
  proc.terminate()
  try:proc.wait(timeout=20)
  except subprocess.TimeoutExpired:
   os.killpg(proc.pid,signal.SIGKILL);proc.wait(timeout=10)
def main():
 assert socket.gethostname().split('.')[0]=='trace-build500'
 window=json.loads((Path.home()/'beam/authorized-window.json').read_text())
 started=time.time()
 assert window['authorized'] is True and window['host']=='trace-build500'
 assert parseutc(window['not_before_utc'])<=started<parseutc(window['not_after_utc'])
 assert started<LATEST_START,'this supervisor qualification start window closed'
 gate=json.loads((ROOT/'LOCAL-1M-GATE.json').read_text())
 assert gate['status']=='PASS' and gate['target_tokens']==1000000 and gate['manifest_match'] is True
 freeze_path=ROOT/'SOURCEFREEZE.json';freeze=json.loads(freeze_path.read_text())['files']
 freeze_hash=hashlib.sha256(freeze_path.read_bytes()).hexdigest()
 assert gate['source_freeze_sha256']==freeze_hash,'gate source freeze changed'
 assert gate['frozen_files']==freeze and freeze,'gate must cover complete frozen source'
 products={n:d for n,d in freeze.items() if n.startswith('fork/')}
 assert gate['product_files']==products and products,'gate must cover all product source'
 for name,digest in freeze.items():
  assert not Path(name).is_absolute() and '..' not in Path(name).parts
  assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
 assert memkb()>=16*1024**2
 disk=os.statvfs(ROOT);assert disk.f_bavail*disk.f_frsize>=80*1024**3
 deadline=min(DEADLINE,parseutc(window['not_after_utc'])-300,started+12*3600)
 budget=int(deadline-started);assert budget>120,'past bounded qualification start margin'
 data=Path.home()/'beam/pkg/data';assert (data/'docs-100m.jsonl').is_file() and (data/'emb_cache/meta.json').is_file()
 env=dict(os.environ,OMP_NUM_THREADS='1',OPENBLAS_NUM_THREADS='1',MKL_NUM_THREADS='1',PYTHONDONTWRITEBYTECODE='1')
 env['TMPDIR']=str(ROOT/'tmp');env['PYTHONPATH']=str(ROOT/'fork/tl-sys')+':'+str(ROOT/'tools')
 if hasattr(os,'sched_setaffinity'):
  cpus={12,13,14,15}&os.sched_getaffinity(0);assert cpus,'no qualification CPU allocation';os.sched_setaffinity(0,cpus)
 command=['timeout','--signal=TERM','--kill-after=10',str(budget),'nice','-n','19',str(Path.home()/'venv/bin/python'),'-B',str(ROOT/'tools/product_pilot.py'),'--tokens','10000000','--profile','vm','--source-root',str(ROOT),'--data-dir',str(data),'--out',str(ROOT/'receipts/vm-10m')]
 with (ROOT/'vm-10m.log').open('x') as out:
  proc=subprocess.Popen(command,cwd=ROOT,env=env,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
  try:
   save('vm-start.json',{'utc':utc(),'pid':proc.pid,'driver_pid':os.getpid(),'budget_s':budget,'deadline_utc':datetime.datetime.fromtimestamp(deadline,UTC).isoformat(),'host':socket.gethostname(),'mem_available_kb':memkb(),'local_gate':gate,'source_freeze_sha256':freeze_hash,'data':str(data),'affinity':sorted(os.sched_getaffinity(0)),'user_authorization':'2026-10-11 user update: existing VM 10M qualification; bounded across supervisor handoff'})
   while proc.poll() is None:
    save('vm-status.json',{'utc':utc(),'pid':proc.pid,'rc':None,'deadline_utc':datetime.datetime.fromtimestamp(deadline,UTC).isoformat(),'mem_available_kb':memkb(),'elapsed_s':time.time()-started,'progress':progress()})
    if memkb()<16*1024**2 or time.time()>=deadline:stop(proc)
    else:time.sleep(10)
  finally:stop(proc)
  save('vm-rc.json',{'utc':utc(),'pid':proc.pid,'rc':proc.returncode})
  save('vm-status.json',{'utc':utc(),'pid':proc.pid,'rc':proc.returncode,'mem_available_kb':memkb(),'elapsed_s':time.time()-started,'progress':progress()})
 raise SystemExit(proc.returncode)
if __name__=='__main__':main()
