#!/usr/bin/env python3
"""Initialize a fresh, loopback-only Web UI; keep its random password private."""
import argparse,json,os,pathlib,secrets,sys,time,urllib.request,urllib.parse

def initialize(base,credential_file):
    url=urllib.parse.urlsplit(base)
    if url.scheme!='http' or url.hostname not in {'127.0.0.1','localhost','::1'} or url.username:raise ValueError('loopback endpoint required')
    def post(path,data,token=None):
        headers={'Content-Type':'application/json'}
        if token:headers['Authorization']='Bearer '+token
        r=urllib.request.Request(base+path,json.dumps(data).encode(),headers=headers,method='POST')
        with urllib.request.urlopen(r,timeout=8) as response:return json.load(response)
    login=None
    for _ in range(15):
        try:login=post('/api/auth/login',{'username':'admin','password':'123456'});break
        except OSError:time.sleep(1)
    if not login or not login.get('token'):raise RuntimeError('fresh account initialization failed')
    password=secrets.token_urlsafe(24)
    path=pathlib.Path(credential_file);path.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    if path.is_symlink() or path.exists():raise FileExistsError('credential file already exists')
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:json.dump({'username':'admin','password':password,'url':base,'verified':False},f)
    changed=post('/api/auth/change-password',{'currentPassword':'123456','newPassword':password},login['token'])
    if changed.get('success') is not True:raise RuntimeError('password update failed')
    verified=post('/api/auth/login',{'username':'admin','password':password})
    if not verified.get('token'):raise RuntimeError('new password authentication failed')
    with path.open('w') as f:json.dump({'username':'admin','password':password,'url':base,'verified':True},f)
    os.chmod(path,0o600)
    print('Web UI random password initialized and authenticated; credentials saved privately.')

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--url',default='http://127.0.0.1:8648');p.add_argument('--credentials',required=True);a=p.parse_args()
    try:initialize(a.url,a.credentials)
    except Exception as e:print('FAILED: Web UI bootstrap '+type(e).__name__,file=sys.stderr);sys.exit(1)
