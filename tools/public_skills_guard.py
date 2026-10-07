#!/usr/bin/env python3
"""Fail-closed checks for a reviewed, immutable public skills snapshot.

This guard does not authorize new source content. Publication also requires
exact source and output hashes in a private approval manifest.
"""
import hashlib
import gzip
import io
import json
import pathlib
import re
import tarfile

PATTERNS = {
    'api_key': re.compile(r'\bsk-(?:proj-|ant-api\d+-)?[A-Za-z0-9_-]{24,}'),
    'github_token': re.compile(r'\b(?:gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,})'),
    'google_secret': re.compile(r'GOCSPX-[A-Za-z0-9_-]{20,}'),
    'google_api_key': re.compile(r'AIza[0-9A-Za-z_-]{35}'),
    'oauth_token': re.compile(r'ya29\.[A-Za-z0-9_.-]{20,}'),
    'aws_access_key': re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
    'telegram_token': re.compile(r'(?<![\w])\d{7,12}:[A-Za-z0-9_-]{30,50}'),
    'telegram_api_hash': re.compile(
        r'''(?i)\b(?:[a-z][a-z0-9]*_)*api_hash\b["']?\s*'''
        r'''(?::\s*str\s*)?(?:=|:)\s*'''
        r'''(?:os\.(?:getenv|environ\.get)\(\s*["'][^"']+["']\s*,\s*)?'''
        r'''["'`]?([a-f0-9]{32})(?![a-f0-9])'''
    ),
    'telegram_client_api_hash': re.compile(
        r'''\bTelegramClient\s*\(\s*[^,\n]+,\s*[^,\n]+,\s*["']([a-fA-F0-9]{32})["']'''
    ),
    'private_key': re.compile(r'-----BEGIN (?:RSA |EC |OPENSSH |ENCRYPTED |DSA )?PRIVATE KEY-----'),
    'jwt': re.compile(r'eyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}'),
    'mtg_secret': re.compile(r'\bee[0-9a-fA-F]{32,}\b'),
    'url_password': re.compile(r'\b(?:https?|socks5?|postgres(?:ql)?|mysql|redis)://[^\s:/<>]+:[^\s/@<>]+@'),
    'url_secret': re.compile(r'(?i)[?&](?:secret|token|api_key|password)=([A-Za-z0-9_-]{16,})'),
    'inline_password': re.compile(r'(?:密码|口令|密钥|secret)[\s：:]*`([^`\s]{4,})`', re.I),
}
TEXT_EXTENSIONS = {'.md','.json','.yaml','.yml','.py','.sh','.txt','.js','.mjs','.tex','.sty','.bst','.bib','.html','.service','.conf','.ini'}
TEXT_NAMES = {'LICENSE','Makefile'}

class GuardError(Exception):
    """Message is safe for logs: names and types, never matched values."""

def sha(data):return hashlib.sha256(data).hexdigest()

def placeholder(value):
    if value.startswith('<') and value.endswith('>'):
        return bool(re.fullmatch(r'<[A-Z0-9_ /:.()-]+>',value))
    if re.fullmatch(r'(?:YOUR|REPLACE_WITH|EXAMPLE|DUMMY|TEST)_[A-Z0-9_]+',value):return True
    if value in {'SecretPassword','YourStrongPasswordHere','TG_2FA_PASSWORD','password','example','<user>:<password>@'}:return True
    if re.fullmatch(r'sk-(?:proj-|ant-api\d+-)?[xX]+',value):return True
    return False

def inspect_text(text,path):
    findings=[]
    for kind,pattern in PATTERNS.items():
        for m in pattern.finditer(text):
            value=m.group(1) if m.lastindex else m.group()
            if placeholder(value):continue
            # Ignore shell/SQL expressions and config identifiers in prose.
            if kind=='inline_password' and (value.startswith(('$','os.getenv','root@')) or any(c in value for c in ('/','(',')','\\','='))):continue
            findings.append({'path':path,'line':text.count('\n',0,m.start())+1,'type':kind})
    return findings

def inspect_archive(data,expected_hashes=None,approved_pdf_hashes=()):
    files={};findings=[];total=0
    try:
        if len(data)>16*1024*1024:raise GuardError('oversized_compressed_archive')
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as gz:
            raw=gz.read(64*1024*1024+1)
        if len(raw)>64*1024*1024:raise GuardError('oversized_uncompressed_archive')
        archive=tarfile.open(fileobj=io.BytesIO(raw),mode='r:')
        with archive:
            for n,m in enumerate(archive):
                if n>=2500:raise GuardError('too_many_archive_members')
                p=pathlib.PurePosixPath(m.name)
                if p.is_absolute() or '..' in p.parts or '\\' in m.name or not p.parts or p.parts[0]!='skills':raise GuardError('unsafe_archive_path')
                if m.isdir():continue
                if not m.isfile() or m.issym() or m.islnk():raise GuardError('nonregular_archive_member')
                if m.name in files:raise GuardError('duplicate_archive_member')
                if m.size>8*1024*1024:raise GuardError('oversized_archive_member')
                total+=m.size
                if total>64*1024*1024:raise GuardError('oversized_archive')
                if any(part.startswith('.') for part in p.parts):raise GuardError('hidden_archive_member')
                if p.suffix=='.pdf':
                    b=archive.extractfile(m).read()
                    if sha(b) not in approved_pdf_hashes:raise GuardError('unreviewed_pdf')
                else:
                    if p.suffix not in TEXT_EXTENSIONS and p.name not in TEXT_NAMES:raise GuardError('unsupported_archive_file')
                    b=archive.extractfile(m).read()
                    try:text=b.decode('utf-8',errors='strict')
                    except UnicodeError:raise GuardError('undecodable_archive_member') from None
                    if '\0' in text:raise GuardError('binary_in_text_member')
                    findings.extend(inspect_text(text,m.name))
                files[m.name]=sha(b)
        if not files:raise GuardError('empty_archive')
        if expected_hashes is not None and files!=expected_hashes:raise GuardError('unapproved_archive_content')
        if findings:raise GuardError(json.dumps({'credential_findings':findings[:30],'total':len(findings)},ensure_ascii=False))
        return files
    except (tarfile.TarError,EOFError,OSError) as e:
        raise GuardError('archive_scan_failed:'+type(e).__name__) from None

def verify_source(root,expected_hashes):
    root=pathlib.Path(root)
    if not root.is_dir() or root.is_symlink():raise GuardError('source_directory_unavailable')
    actual={}
    for p in root.rglob('*'):
        rel=p.relative_to(root)
        if any(x in {'.git','.curator_backups','__pycache__','.hub'} for x in rel.parts):continue
        if p.is_symlink():raise GuardError('source_symlink')
        if not p.is_file():continue
        if p.name in {'.curator_state','.bundled_manifest','curator.lock','.usage.json.lock','.usage.json','.webui-managed-skills.json'}:continue
        if p.name.endswith(('.bak','.tmp','.log','.pyc')) or re.search(r'\.db(?:\.|$)',p.name):continue
        name='skills/'+rel.as_posix()
        if name not in expected_hashes:raise GuardError('unapproved_source_file:'+name)
        actual[name]=sha(p.read_bytes())
    if actual!=expected_hashes:
        changed=sorted(k for k in set(actual)|set(expected_hashes) if actual.get(k)!=expected_hashes.get(k))
        raise GuardError('source_requires_review:'+','.join(changed[:15]))
    return actual

if __name__=='__main__':
    import argparse,sys
    p=argparse.ArgumentParser();p.add_argument('bundle');p.add_argument('manifest');a=p.parse_args()
    try:
        manifest=json.loads(pathlib.Path(a.manifest).read_text())
        data=pathlib.Path(a.bundle).read_bytes()
        if sha(data)!=manifest['bundle_sha256']:raise GuardError('bundle_hash_mismatch')
        files=inspect_archive(data,manifest['output_hashes'],manifest['pdf_hashes'])
        print(json.dumps({'scan':'PASS','files':len(files),'bundle_sha256':sha(data)}))
    except (GuardError,OSError,KeyError,ValueError) as e:
        print('FAILED: '+str(e),file=sys.stderr);sys.exit(1)
