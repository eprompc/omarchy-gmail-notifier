import importlib.util
import json
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'helper'))
from service import Service
spec=importlib.util.spec_from_file_location('notifier_service', Path(__file__).resolve().parents[1] / 'helper/main.py')
h=importlib.util.module_from_spec(spec);spec.loader.exec_module(h)


class FakeClient:
    def __init__(self): self.messages=[]
    def sendall(self, data): self.messages.append(json.loads(data))


class ServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.directory=Path(self.temp.name)
        for key,value in {'APP_DIR':self.directory,'CONFIG_PATH':self.directory/'config.json',
                          'SNAPSHOT_PATH':self.directory/'snapshot.json','OAUTH_CLIENT_PATH':self.directory/'oauth-client.json'}.items():
            p=patch.object(h,key,value);p.start();self.addCleanup(p.stop)
        h.save_config(dict(h.DEFAULT_CONFIG,accounts=[dict(id='a',email='a@example.invalid',initial='A',enabled=False,notifications=False)]))
        self.service=Service(h)

    def test_multiple_clients_receive_identical_ordered_revisions(self):
        clients=[FakeClient(),FakeClient(),FakeClient()]
        self.service.clients={c:True for c in clients}
        self.service.publish()
        self.service.execute(['set-initial','a','TR'])
        states=[[m for m in c.messages if m['type']=='state'] for c in clients]
        self.assertEqual(states[0],states[1]);self.assertEqual(states[1],states[2])
        self.assertEqual([m['revision'] for m in states[0]], [1,2])
        self.assertEqual(states[0][-1]['accounts'][0]['initial'],'TR')

    def test_idle_unchanged_publish_does_not_emit_or_write(self):
        client=FakeClient();self.service.clients={client:True}
        self.service.publish();stamp=h.CONFIG_PATH.stat().st_mtime_ns
        self.service.publish();self.service.publish()
        self.assertEqual(len(client.messages),1);self.assertEqual(h.CONFIG_PATH.stat().st_mtime_ns,stamp)

    def test_acknowledgement_does_not_wait_for_network_worker(self):
        from alerts import AlertStore
        store=AlertStore(self.directory);store.observe('a',['old'],True,60);store.observe('a',['new'],True,60)
        event=store.read()['a']['event_id']
        blocked=threading.Event();release=threading.Event()
        real_call=self.service.run_network
        def call(args):
            if args==['update']: blocked.set();release.wait(3);return {'ok':True}
            return real_call(args)
        self.service.run_network=call
        worker=threading.Thread(target=self.service.worker,daemon=True);worker.start()
        self.service.jobs.put((['update'],None,None));self.assertTrue(blocked.wait(1))
        self.service.request({'args':['ack-alert','a',event],'request_id':0},None)
        self.assertTrue(store.read()['a']['acknowledged'])
        release.set();self.service.stop.set();worker.join(3)

    def test_real_private_socket_transports_action_without_argv(self):
        # socketpair exercises the same server client handler and private JSON protocol.
        server,client=socket.socketpair();client.settimeout(3)
        thread=threading.Thread(target=self.service.client,args=(server,),daemon=True);thread.start()
        with client,client.makefile('rb') as stream:
            self.assertEqual(json.loads(stream.readline())['type'],'state')
            client.sendall(b'{"args":["set-initial","a","TR"],"request_id":1}\n')
            self.assertEqual(json.loads(stream.readline())['accounts'][0]['initial'],'TR')
            self.assertTrue(json.loads(stream.readline())['ok'])
        thread.join(3)

    def test_two_persistent_watchers_share_one_service(self):
        import os, subprocess, select
        from service import socket_path
        with patch.dict(os.environ, {'XDG_RUNTIME_DIR': str(self.directory)}):
            thread=threading.Thread(target=self.service.run,daemon=True);thread.start()
            path=socket_path(h)
            deadline=time.monotonic()+3
            while not path.exists() and time.monotonic()<deadline: time.sleep(0.02)
            processes=[]
            try:
                for _ in range(2):
                    p=subprocess.Popen([sys.executable,str(Path(h.__file__)),'watch'],stdin=subprocess.PIPE,
                                       stdout=subprocess.PIPE,stderr=subprocess.PIPE,env=os.environ.copy())
                    processes.append(p)
                    self.assertTrue(select.select([p.stdout],[],[],3)[0])
                    self.assertEqual(json.loads(p.stdout.readline())['type'],'state')
                processes[0].stdin.write(b'{"args":["set-initial","a","WORK"],"request_id":1}\n')
                processes[0].stdin.flush()
                # The second client receives a shared state with the edit, without a poll request.
                self.assertTrue(select.select([processes[1].stdout],[],[],3)[0])
                self.assertEqual(json.loads(processes[1].stdout.readline())['accounts'][0]['initial'],'WORK')
                self.assertTrue(all(p.args[-1]=='watch' for p in processes))
            finally:
                for p in processes:
                    p.stdin.close();p.wait(timeout=3);p.stdout.close();p.stderr.close()
                self.service.stop.set();thread.join(3)

    def test_code_update_uses_new_backend_without_moving_personal_state(self):
        from types import SimpleNamespace
        from service import socket_path
        source=self.directory/'source';source.mkdir()
        script=source/'main.py';script.write_text('# old backend')
        helper=SimpleNamespace(APP_DIR=self.directory,__file__=str(script))
        first=socket_path(helper)
        script.write_text('# updated backend')
        second=socket_path(helper)
        self.assertNotEqual(first,second)
        self.assertEqual(first.parent,second.parent)
        self.assertNotEqual(first.with_suffix('.lock'),second.with_suffix('.lock'))
        self.assertEqual(helper.APP_DIR,self.directory)
