"""Supervisor regressions for actual visibility, cold attach and concurrent ACKs."""
import tempfile,time,threading,unittest
from contextlib import contextmanager
from pathlib import Path
from tlsys.store_if import TLStore
from tlsys.ingest import ingest_docs
from tlsys.maint import organize_segments
from tlsys.org_service import OrganizationService,ServiceConfig
from tlsys.org_publication import GenerationPublisher

def embed(texts):return [[1.,0.,0.,0.] if t=='old topic' else [0.,1.,0.,0.] for t in texts]
class Acceptance(unittest.TestCase):
 def setUp(self):
  self.root=Path(tempfile.mkdtemp(prefix='supervisor-acceptance-'))
  self.tl=TLStore(str(self.root/'store'),create=True)
  ingest_docs(self.tl,[('old','old topic')],embed,place_xdoc=False)
  organize_segments(self.tl)
  self.s=OrganizationService(self.tl,config=ServiceConfig(enabled=True,await_visibility_on_ack=True),directory=self.root/'service')
  self.s.publish().result()
 def tearDown(self):self.s.close();self.tl.close()
 def test_pending_best_result_survives_full_guided_topk(self):
  ack=self.s.ingest_visible([('new','new topic')],embed,place_xdoc=False)
  with self.s.publisher.acquire() as pin:
   rows,rep=pin.facade.search('new topic',[0.,1.,0.,0.],k=1,top_atoms=10)
   self.assertEqual(rows[0]['doc_id'],'new')
   self.assertEqual(rep['generation'],ack['generation'].pin[3])
 def test_cold_submit_installs_runtime_without_new_disk_generation(self):
  old=self.s.publisher.load_record();directory=self.s.publisher.directory
  self.s.publisher.close();self.s.publisher=GenerationPublisher(self.tl,directory)
  new=self.s.publisher.submit(self.tl.pin(),self.s.pending()).result()
  self.assertEqual(new,old)
  with self.s.publisher.acquire() as pin:
   rows,_=pin.facade.guided('old',[1.,0.,0.,0.]);self.assertTrue(rows)
 def test_source_delay_excludes_slow_source_ingest(self):
  def slow(texts):time.sleep(.15);return embed(texts)
  ack=self.s.ingest_visible([('slow','new topic')],slow,place_xdoc=False)
  self.assertGreater(ack['total_ingest_to_ack_s']-ack['source_commit_to_ack_s'],.14)
  self.assertEqual(ack['generation'].pin[3],ack['ack']['pinned'])
 def test_search_k_reaches_organized_results_above_default_ten(self):
  docs=[('many-'+str(i),'new topic') for i in range(21)]
  self.s.ingest_visible(docs,embed,place_xdoc=False)
  self.s.drain(max_documents=32,budget_seconds=60);self.s.last_future.result()
  with self.s.publisher.acquire() as pin:
   rows,rep=pin.facade.search('topic',[0.,1.,0.,0.],k=20)
   self.assertEqual(len(rows),20)
   self.assertEqual(len({r['aid'] for r in rows}),20)
 def test_concurrent_acks_bind_their_own_source_frontiers(self):
  original=self.s._writer;unlocked=threading.Event();second_done=threading.Event()
  @contextmanager
  def ordered_exit():
   with original():yield
   if threading.current_thread().name=='ack-first':
    unlocked.set();self.assertTrue(second_done.wait(10))
  self.s._writer=ordered_exit
  results=[];errors=[]
  def work(doc):
   try:results.append(self.s.ingest_visible([(doc,'new topic')],embed,place_xdoc=False))
   except BaseException as e:errors.append(str(e))
   finally:
    if doc=='concurrent-b':second_done.set()
  first=threading.Thread(target=work,args=('concurrent-a',),name='ack-first')
  second=threading.Thread(target=work,args=('concurrent-b',),name='ack-second')
  first.start();self.assertTrue(unlocked.wait(10));second.start()
  first.join(10);second.join(10)
  self.assertFalse(first.is_alive());self.assertFalse(second.is_alive())
  self.assertFalse(errors);self.assertEqual(len(results),2)
  for ack in results:self.assertEqual(ack['generation'].pin[3],ack['ack']['pinned'])
if __name__=='__main__':unittest.main(verbosity=2)
