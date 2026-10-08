import io,json,os,pathlib,subprocess,sys,tempfile,unittest
from unittest.mock import patch
from test_installer_preflight import SOURCE,function
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]/'tools'))
from sync_telegram_menu import sync,PUBLIC_COMMANDS

class SecurityTests(unittest.TestCase):
    def test_revision_must_exist_and_match_installer(self):
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d);(root/'install.sh').write_text('reviewed')
            def git(*args):return subprocess.check_output(['git','-C',d,*args]).decode().strip()
            git('init','-q');git('add','install.sh')
            git('-c','user.name=Test','-c','user.email=test@example.invalid','commit','-qm','fixture')
            sha=git('rev-parse','HEAD')
            def run(revision):
                env=dict(os.environ,SCRIPT_DIR=d,STARTER_REVISION=revision)
                return subprocess.run(['bash','-euo','pipefail','-c',function('assert_reviewed_revision')+'\nassert_reviewed_revision'],env=env,capture_output=True,text=True)
            self.assertEqual(run(sha).returncode,0)
            for revision in ['', 'main', '0'*40]:self.assertNotEqual(run(revision).returncode,0)
            (root/'install.sh').write_text('modified')
            self.assertNotEqual(run(sha).returncode,0)

    def test_download_mismatch_and_missing_pin_fail(self):
        with tempfile.TemporaryDirectory() as d:
            p=pathlib.Path(d)/'external.sh';p.write_text('untrusted')
            result=subprocess.run(['bash','-euc',function('verify_download')+'\nverify_download "$1" "$2"\necho EXECUTED','test',str(p),'0'*64],capture_output=True,text=True)
            self.assertNotEqual(result.returncode,0);self.assertNotIn('EXECUTED',result.stdout)
        env=dict(os.environ);env.pop('HERMES_INSTALLER_SHA256',None)
        result=subprocess.run(['bash','-euc',function('assert_dependency_pins')+'\nassert_dependency_pins'],env=env,capture_output=True,text=True)
        self.assertNotEqual(result.returncode,0)

    def test_configuration_binds_loopback_and_limits_nonowners(self):
        stage='cat <<EOF > "$H/config.yaml"'+SOURCE.split('cat <<EOF > "$H/config.yaml"',1)[1].split('chown -R',1)[0]
        with tempfile.TemporaryDirectory() as d:
            env=dict(os.environ,H=d,MODEL_YAML='"test"',BASE_URL_YAML='"http://127.0.0.1/v1"',API_KEY_YAML='"TEST_ONLY"',API_SERVER_KEY='LOCAL_ONLY',CFG_TG_TOKEN='TEST',CFG_TG_ADMIN='12345')
            result=subprocess.run(['bash','-euc',stage],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            config=(pathlib.Path(d)/'config.yaml').read_text()
            self.assertIn('host: "127.0.0.1"',config)
            self.assertIn('group_user_allowed_commands: help,whoami\n',config)
            self.assertEqual(config.count('TEST_ONLY'),1)

class MenuTests(unittest.TestCase):
    def env_file(self,d):
        path=pathlib.Path(d)/'.env'
        token='123456789:'+('a'*35)
        path.write_text('TELEGRAM_BOT_TOKEN='+json.dumps(token)+'\nTELEGRAM_ALLOWED_USERS=123456\n');path.chmod(0o600)
        return path,token

    def test_owner_only_extended_menu_and_retry_idempotence(self):
        class Opener:
            def __init__(self):self.calls=[]
            def open(self,request,timeout):
                self.calls.append(json.loads(request.data));return io.BytesIO(b'{"ok":true}')
        with tempfile.TemporaryDirectory() as d,patch('sys.stdout',new_callable=io.StringIO) as output:
            path,token=self.env_file(d);opener=Opener();sync(path,opener);sync(path,opener)
            self.assertEqual(opener.calls[:4],opener.calls[4:])
            for item in opener.calls[:3]:self.assertEqual(item['commands'],PUBLIC_COMMANDS)
            self.assertEqual(opener.calls[3]['scope'],{'type':'chat','chat_id':123456})
            self.assertNotIn(token,output.getvalue())

    def test_rejected_api_preserves_credentials(self):
        class Opener:
            def open(self,*args,**kwargs):return io.BytesIO(b'{"ok":false}')
        with tempfile.TemporaryDirectory() as d:
            path,token=self.env_file(d);before=path.read_bytes()
            with self.assertRaises(RuntimeError):sync(path,Opener())
            self.assertEqual(path.read_bytes(),before)

    def test_failed_menu_stage_does_not_reinstall_or_report_success(self):
        stage=SOURCE.split('# 菜单是可重试的附加步骤',1)[1].split('\n',1)[1].split('echo ""',1)[0]
        with tempfile.TemporaryDirectory() as d:
            root=pathlib.Path(d);(root/'starter-tools').mkdir()
            (root/'starter-tools/sync_telegram_menu.py').write_text('raise SystemExit(1)')
            env=dict(os.environ,H=d,CFG_TG_TOKEN='TEST',TARGET_USER=str(os.getuid()))
            result=subprocess.run(['bash','-euc',stage],env=env,capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)
            self.assertEqual((root/'starter-tools/telegram-menu-status').read_text(),'FAILED\n')
            self.assertIn('FAILED',result.stderr)

if __name__=='__main__':unittest.main()
