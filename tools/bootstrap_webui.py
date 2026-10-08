#!/usr/bin/env python3
"""Initialize or recover a loopback Web UI, retaining its saved password."""
import argparse,json,os,pathlib,secrets,sys,tempfile,time,urllib.request,urllib.parse

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):raise ValueError('redirect refused')

def initialize(base,credential_file):
    url=urllib.parse.urlsplit(base)
    if (url.scheme!='http' or url.hostname not in {'127.0.0.1','::1'} or url.username
        or url.password or url.path not in {'','/'} or url.query or url.fragment):
        raise ValueError('numeric loopback endpoint required')
    base=base.rstrip('/')
    opener=urllib.request.build_opener(urllib.request.ProxyHandler({}),NoRedirect())
    path=pathlib.Path(credential_file)
    if any(p.is_symlink() for p in [path,*path.parents]):raise ValueError('symlink credentials refused')
    path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    if path.exists():
        info=path.stat()
        if not path.is_file() or info.st_uid!=os.getuid() or info.st_mode&0o077:raise ValueError('private credentials required')
        saved=json.loads(path.read_text())
        if saved.get('username')!='admin' or saved.get('url')!=base:raise ValueError('credentials endpoint mismatch')
        password=saved['password']
        if not isinstance(password,str) or len(password)<30:raise ValueError('invalid saved password')
    else:
        password=secrets.token_urlsafe(24)
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as output:
            json.dump({'username':'admin','password':password,'url':base,'verified':False},output)
            output.flush();os.fsync(output.fileno())
    def post(endpoint,data,token=None):
        headers={'Content-Type':'application/json'}
        if token:headers['Authorization']='Bearer '+token
        request=urllib.request.Request(base+endpoint,json.dumps(data).encode(),headers,method='POST')
        with opener.open(request,timeout=8) as response:return json.load(response)
    def login(value):
        result=post('/api/auth/login',{'username':'admin','password':value})
        if not result.get('token'):raise RuntimeError('authentication failed')
        return result['token']
    verified=False
    for attempt in range(15):
        try:login(password);verified=True;break
        except OSError:pass
        try:
            token=login('123456')
            changed=post('/api/auth/change-password',{'currentPassword':'123456','newPassword':password},token)
            if changed.get('success') is not True:raise RuntimeError('password update failed')
            login(password);verified=True;break
        except OSError:
            if attempt<14:time.sleep(1)
    if not verified:raise RuntimeError('initialization failed; saved credentials retained')
    # Do not truncate the recovery password if the final write is interrupted.
    fd,temp_name=tempfile.mkstemp(prefix='.webui-credentials-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as output:
            json.dump({'username':'admin','password':password,'url':base,'verified':True},output)
            output.flush();os.fsync(output.fileno())
        os.replace(temp_name,path)
    finally:
        if os.path.exists(temp_name):os.unlink(temp_name)
    print('SUCCESS: Web UI random password authenticated; credentials saved privately.')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--url',default='http://127.0.0.1:8648');parser.add_argument('--credentials',required=True);args=parser.parse_args()
    try:initialize(args.url,args.credentials)
    except Exception as error:
        print('FAILED: Web UI bootstrap '+type(error).__name__,file=sys.stderr);sys.exit(1)
