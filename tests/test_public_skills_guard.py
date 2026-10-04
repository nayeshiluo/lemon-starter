import io,json,pathlib,sys,tarfile,tempfile,unittest
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
from public_skills_guard import GuardError,inspect_archive,inspect_text,verify_source,sha

def archive(entries):
    buf=io.BytesIO()
    with tarfile.open(fileobj=buf,mode='w:gz') as t:
        for name,data,kind in entries:
            m=tarfile.TarInfo(name)
            if kind=='symlink':m.type=tarfile.SYMTYPE;m.linkname='/etc/passwd';t.addfile(m)
            else:m.size=len(data);t.addfile(m,io.BytesIO(data))
    return buf.getvalue()

class CredentialRegression(unittest.TestCase):
    def test_original_bypass_formats_are_detected(self):
        cases=[
            'api_key=sk-'+('Q'*40),
            'api_key=sk-proj-'+('Q_'*25),
            'api_key=sk-ant-api03-'+('Q_'*25),
            'token=github_pat_'+('Q_'*40),
            'bot_token=1234567890:'+('Q_'*17)+'Q',
            '-----BEGIN PRIVATE KEY-----\nDUMMY\n-----END PRIVATE KEY-----',
            'Authorization: Bearer *** real_key=sk-'+('Q'*40),
            'client_secret=GOCSPX-'+('Q'*30),
            'secret：`ee'+('ab'*16)+'6974756e65732e6170706c652e636f6d`',
            '账号 `admin`，密码 `SensitiveExample123`',
            'https://t.me/proxy?server=example.com&secret='+('ab'*32),
        ]
        for text in cases:
            with self.subTest(text_type=text.split('=')[0][:20]):self.assertTrue(inspect_text(text,'fixture.md'))
    def test_many_hits_do_not_short_circuit_to_success(self):
        hits=inspect_text(('sk-'+('Q'*40)+'\n')*20000,'fixture.md')
        self.assertEqual(len(hits),20000)
    def test_errors_never_disclose_values(self):
        value='sk-proj-'+('Q_'*25)
        with self.assertRaises(GuardError) as caught:inspect_archive(archive([('skills/a.md',value.encode(),'file')]))
        self.assertNotIn(value,str(caught.exception));self.assertIn('api_key',str(caught.exception))
    def test_placeholder_is_not_whole_line_whitelist(self):
        self.assertFalse(inspect_text('Bearer *** api_key=<YOUR_API_KEY> sk-xxxxxxxxxxxxxxxxxxxxxxxx','fixture.md'))
        self.assertTrue(inspect_text('Bearer *** sk-'+('Q'*40),'fixture.md'))

class ArchiveAndApprovalRegression(unittest.TestCase):
    def test_unreadable_or_invalid_archive_fails(self):
        with self.assertRaises(GuardError):inspect_archive(b'broken gzip data')
    def test_traversal_symlink_duplicate_and_hidden_fail(self):
        for entries in [
            [('../outside.md',b'safe','file')],
            [('/skills/a.md',b'safe','file')],
            [('skills/a.md',b'', 'symlink')],
            [('skills/a.md',b'one','file'),('skills/a.md',b'two','file')],
            [('skills/.env',b'password=generic-new-secret','file')],
            [('skills/login.session',b'binary session','file')],
            [('skills/nested.zip',b'binary nested','file')],
            [('skills/a.md',b'\xff','file')],
        ]:
            with self.subTest(path=entries[0][0]),self.assertRaises(GuardError):inspect_archive(archive(entries))
    def test_unreviewed_pdf_and_changed_archive_fail(self):
        with self.assertRaises(GuardError):inspect_archive(archive([('skills/a.pdf',b'%PDF-DUMMY','file')]))
        good=archive([('skills/a.md',b'approved','file')]);manifest={'skills/a.md':sha(b'approved')}
        self.assertEqual(inspect_archive(good,manifest),manifest)
        with self.assertRaises(GuardError):inspect_archive(archive([('skills/a.md',b'changed','file')]),manifest)
    def test_source_addition_change_removal_and_missing_fail(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d)/'skills';root.mkdir();p=root/'a.md';p.write_text('reviewed')
            expected={'skills/a.md':sha(b'reviewed')};self.assertEqual(verify_source(root,expected),expected)
            p.write_text('changed')
            with self.assertRaises(GuardError):verify_source(root,expected)
            p.write_text('reviewed');(root/'.env').write_text('new secret')
            with self.assertRaises(GuardError):verify_source(root,expected)
            (root/'.env').unlink();p.unlink()
            with self.assertRaises(GuardError):verify_source(root,expected)
            with self.assertRaises(GuardError):verify_source(root/'missing',expected)
    def test_reviewed_current_bundle(self):
        root=pathlib.Path(__file__).resolve().parents[1]
        manifest=json.loads((root/'skills_bundle.manifest.json').read_text());data=(root/'skills_bundle.tar.gz').read_bytes()
        self.assertEqual(sha(data),manifest['bundle_sha256'])
        files=inspect_archive(data,manifest['output_hashes'],manifest['pdf_hashes'])
        self.assertEqual(sum(n.endswith('/SKILL.md') for n in files),112)

if __name__=='__main__':unittest.main()
