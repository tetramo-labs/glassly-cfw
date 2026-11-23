"""Loopback-only CLI checks; no Android/ADB/Bluetooth calls."""
import json,pathlib,socket,subprocess,sys,tempfile,threading,unittest
ROOT=pathlib.Path(__file__).resolve().parents[1]
class ControlTests(unittest.TestCase):
 def run_client(self,commands):
  captured=[];errors=[]
  with socket.socket() as server,tempfile.TemporaryDirectory() as temp:
   server.bind(('127.0.0.1',0));server.listen(1);server.settimeout(5)
   token=pathlib.Path(temp)/'token';token.write_text('f'*32)
   def serve():
    try:
     with server.accept()[0] as sock:
      sock.settimeout(5);f=sock.makefile('rb')
      first=json.loads(f.readline());captured.append(first)
      sock.sendall((json.dumps({'id':'hello','ok':True,'result':{'protocol':1}})+'\n').encode())
      for line in f:captured.append(json.loads(line))
    except Exception as e:errors.append(e)
   t=threading.Thread(target=serve);t.start()
   run=subprocess.run([sys.executable,str(ROOT/'control.py'),'--token-file',str(token),'--port',str(server.getsockname()[1])],input=commands,text=True,capture_output=True,timeout=8)
   t.join(6);self.assertFalse(t.is_alive());self.assertEqual(errors,[]);self.assertEqual(run.returncode,0,run.stderr)
   self.assertNotIn('f'*32,run.stdout+run.stderr)
   return captured,run
 def test_eof_never_starts_or_types(self):
  seen,_=self.run_client('');self.assertEqual([q['op'] for q in seen],['hello'])
 def test_only_explicit_request(self):
  seen,_=self.run_client('{"op":"status"}\n');self.assertEqual([q['op'] for q in seen],['hello','status']);self.assertEqual(seen[1]['id'],1)
 def test_unknown_and_oversized_requests_not_sent(self):
  seen,run=self.run_client('{"op":"pair"}\n'+json.dumps({'op':'report','hex':'00'*3000})+'\n');self.assertEqual(len(seen),1);self.assertIn('invalid operation',run.stderr);self.assertIn('too long',run.stderr)
if __name__=='__main__':unittest.main()
