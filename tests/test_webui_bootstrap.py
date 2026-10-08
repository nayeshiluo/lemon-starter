import contextlib,http.server,io,json,pathlib,sys,tempfile,threading,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
from bootstrap_webui import initialize

class BootstrapTests(unittest.TestCase):
    def test_http_authentication_and_private_credential_file(self):
        state={'password':'123456','changed':False}
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                data=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if self.path=='/api/auth/login':
                    ok=data['username']=='admin' and data['password']==state['password']
                    result={'token':'mock-session-token'} if ok else {'error':'denied'}
                else:
                    ok=self.headers.get('Authorization')=='Bearer mock-session-token' and data['currentPassword']==state['password']
                    if ok:state['password']=data['newPassword'];state['changed']=True
                    result={'success':ok}
                body=json.dumps(result).encode();self.send_response(200 if ok else 401);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
        server=http.server.HTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as d,contextlib.redirect_stdout(io.StringIO()) as output:
                p=pathlib.Path(d)/'credentials.json'
                initialize('http://127.0.0.1:'+str(server.server_port),p)
                data=json.loads(p.read_text());self.assertTrue(state['changed']);self.assertTrue(data['verified'])
                self.assertEqual(p.stat().st_mode&0o777,0o600);self.assertGreaterEqual(len(data['password']),30)
                self.assertNotEqual(data['password'],'123456');self.assertNotIn(data['password'],output.getvalue())
                # Retry after a previous success must keep the existing password.
                initialize('http://127.0.0.1:'+str(server.server_port),p)
                self.assertEqual(json.loads(p.read_text())['password'],data['password'])
                self.assertNotIn(data['password'],output.getvalue())
        finally:server.shutdown();server.server_close();thread.join()
    def test_public_endpoint_is_refused(self):
        with self.assertRaises(ValueError):initialize('http://198.51.100.1:8648','not-created.json')

    def test_pending_password_survives_interrupted_initialization(self):
        from unittest.mock import patch
        class Opener:
            def open(self,request,timeout):
                data=json.loads(request.data)
                if data.get('password')=='p'*32:return io.BytesIO(b'{"token":"test"}')
                raise AssertionError('must authenticate saved password first')
        with tempfile.TemporaryDirectory() as d,patch('urllib.request.build_opener',return_value=Opener()),contextlib.redirect_stdout(io.StringIO()):
            p=pathlib.Path(d)/'credentials.json'
            p.write_text(json.dumps({'username':'admin','password':'p'*32,'url':'http://127.0.0.1:8648','verified':False}));p.chmod(0o600)
            initialize('http://127.0.0.1:8648',p)
            data=json.loads(p.read_text());self.assertTrue(data['verified']);self.assertEqual(data['password'],'p'*32)

    def test_symlink_and_broad_permissions_are_refused_without_request(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as d,patch('urllib.request.build_opener') as opener:
            p=pathlib.Path(d)/'credentials.json';other=pathlib.Path(d)/'other'
            other.write_text('keep');p.symlink_to(other)
            with self.assertRaises(ValueError):initialize('http://127.0.0.1:8648',p)
            self.assertEqual(other.read_text(),'keep');opener.return_value.open.assert_not_called()
            p.unlink();p.write_text('{}');p.chmod(0o644)
            with self.assertRaises(ValueError):initialize('http://127.0.0.1:8648',p)
            opener.return_value.open.assert_not_called()

    def test_redirect_is_refused(self):
        class Handler(http.server.BaseHTTPRequestHandler):
            def log_message(self,*args):pass
            def do_POST(self):
                self.send_response(307);self.send_header('Location','http://198.51.100.1/collect');self.end_headers()
        server=http.server.HTTPServer(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with tempfile.TemporaryDirectory() as d,self.assertRaises(ValueError):
                initialize('http://127.0.0.1:'+str(server.server_port),pathlib.Path(d)/'credentials.json')
        finally:server.shutdown();server.server_close();thread.join()

    def test_final_write_failure_retains_recovery_password(self):
        from unittest.mock import patch
        class Opener:
            def open(self,*args,**kwargs):return io.BytesIO(b'{"token":"test"}')
        with tempfile.TemporaryDirectory() as d,patch('urllib.request.build_opener',return_value=Opener()):
            p=pathlib.Path(d)/'credentials.json'
            p.write_text(json.dumps({'username':'admin','password':'p'*32,'url':'http://127.0.0.1:8648','verified':False}));p.chmod(0o600)
            before=p.read_bytes()
            with patch('os.replace',side_effect=OSError('simulated write failure')),self.assertRaises(OSError):
                initialize('http://127.0.0.1:8648',p)
            self.assertEqual(p.read_bytes(),before)
            self.assertEqual(list(pathlib.Path(d).glob('.webui-credentials-*')),[])

if __name__=='__main__':unittest.main()
