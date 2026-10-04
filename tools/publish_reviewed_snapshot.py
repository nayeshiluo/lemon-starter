#!/usr/bin/env python3
"""Verify a reviewed snapshot; never publish unseen production skill changes."""
import argparse,fcntl,json,os,pathlib,subprocess,sys,tempfile
from public_skills_guard import GuardError,inspect_archive,verify_source,sha

def private_file(p):
    if p.is_symlink() or not p.is_file():raise GuardError('approval_file_missing')
    s=p.stat()
    if s.st_uid!=os.getuid() or s.st_mode & 0o077:raise GuardError('approval_file_permissions')
    return p.read_bytes()

def run():
    parser=argparse.ArgumentParser();parser.add_argument('--approval-dir',required=True);parser.add_argument('--source',required=True);parser.add_argument('--skip-remote',action='store_true',help='Local verification only; no publication or remote verification')
    a=parser.parse_args();root=pathlib.Path(a.approval_dir)
    if root.is_symlink() or not root.is_dir() or root.stat().st_uid!=os.getuid() or root.stat().st_mode&0o077:raise GuardError('approval_directory_permissions')
    with (root/'publish.lock').open('a') as lock:
        os.chmod(root/'publish.lock',0o600)
        try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError:raise GuardError('another_publication_is_running') from None
        manifest=json.loads(private_file(root/'approval.json'))
        source=verify_source(a.source,manifest['source_hashes'])
        data=private_file(root/'skills_bundle.tar.gz')
        if sha(data)!=manifest['bundle_sha256']:raise GuardError('approved_bundle_hash_mismatch')
        files=inspect_archive(data,manifest['output_hashes'],manifest['pdf_hashes'])
        # Read only this instance's credential file; never log values.
        env=pathlib.Path(a.source).parent/'.env'
        if env.is_file():
            import tarfile,io,re
            values=[]
            for line in env.read_text().splitlines():
                if '=' not in line or line.lstrip().startswith('#'):continue
                key,value=line.split('=',1);value=value.strip().strip('"').strip("'")
                if len(value)>=8 and re.search(r'(?i)key|token|secret|password|hash',key):values.append(value)
            with tarfile.open(fileobj=io.BytesIO(data)) as t:
                for m in t:
                    if not m.isfile() or m.name.endswith('.pdf'):continue
                    content=t.extractfile(m).read().decode('utf-8',errors='strict')
                    if any(v in content for v in values):raise GuardError('live_credential_in_approved_bundle:'+m.name)
        if not a.skip_remote:
            with tempfile.TemporaryDirectory(prefix='reviewed-starter-') as tmp:
                # No existing index or local unpublished commit can enter this checkout.
                q=subprocess.run(['git','clone','--depth','1','--quiet',manifest['remote_url'],tmp],capture_output=True,timeout=90)
                if q.returncode:raise GuardError('remote_checkout_failed')
                head=subprocess.check_output(['git','-C',tmp,'rev-parse','HEAD'],timeout=15).decode().strip()
                if head!=manifest['remote_commit']:raise GuardError('remote_revision_requires_review')
                remote=pathlib.Path(tmp)/'skills_bundle.tar.gz'
                if sha(remote.read_bytes())!=manifest['bundle_sha256']:raise GuardError('remote_bundle_hash_mismatch')
                inspect_archive(remote.read_bytes(),manifest['output_hashes'],manifest['pdf_hashes'])
                actual={str(p.relative_to(tmp)):sha(p.read_bytes()) for p in pathlib.Path(tmp).rglob('*') if p.is_file() and '.git' not in p.relative_to(tmp).parts}
                if actual!=manifest['repository_hashes']:raise GuardError('remote_files_require_review')
        print(json.dumps({'result':'SUCCESS','mode':'local_only' if a.skip_remote else 'reviewed_public_snapshot','skills':sum(p.endswith('/SKILL.md') for p in files),'files':len(files),'source_files':len(source),'bundle_sha256':manifest['bundle_sha256'],'changed_source_policy':'stop_and_require_review'},ensure_ascii=False))

if __name__=='__main__':
    try:run()
    except Exception as e:
        # Unexpected exception text can contain credentials from subprocesses.
        message=str(e) if isinstance(e,GuardError) else type(e).__name__
        print('FAILED: '+message,file=sys.stderr);sys.exit(1)
