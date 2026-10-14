import subprocess,sys,unittest
from pathlib import Path
class VMGuard(unittest.TestCase):
 def test_vm_profile_refuses_local_before_loading_corpus(self):
  import socket
  if socket.gethostname().split('.')[0]=='trace-build500':self.skipTest('run on local supervisor')
  p=subprocess.run([sys.executable,'-B',str(Path(__file__).resolve().parents[1]/'tools/product_pilot.py'),'--tokens','10000000','--profile','vm','--out','/nonexistent/no-write'],capture_output=True,text=True)
  self.assertNotEqual(p.returncode,0);self.assertIn('VM profile requires existing trace-build500',p.stderr)
