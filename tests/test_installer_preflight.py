"""Run installer boundary functions against isolated files and synthetic inputs."""
import os
import pathlib
import re
import subprocess
import tempfile
import unittest

SOURCE = (pathlib.Path(__file__).resolve().parents[1] / 'install.sh').read_text()


def function(name):
    match = re.search(r'^' + name + r'\(\) \{\n.*?^\}', SOURCE, re.M | re.S)
    if not match:
        raise AssertionError('installer boundary function missing: ' + name)
    return match.group()


def fresh(home, units):
    return subprocess.run(['bash', '-c', function('assert_fresh_install') +
                           '\nassert_fresh_install "$1" "$2"', 'test', str(home), str(units)],
                          capture_output=True, text=True)


def config(**changes):
    env = dict(os.environ, CFG_MODEL='test-model', CFG_BASE_URL='https://example.com/v1',
               CFG_API_KEY='TEST_API_KEY', CFG_TG_TOKEN='', CFG_TG_ADMIN='')
    env.update(changes)
    return subprocess.run(['bash', '-c', function('validate_installer_config') +
                           '\nvalidate_installer_config'], env=env, capture_output=True, text=True)


class InstallerPreflightTests(unittest.TestCase):
    def test_clean_destination(self):
        with tempfile.TemporaryDirectory(prefix='hermes preflight ') as tmp:
            self.assertEqual(fresh(pathlib.Path(tmp) / 'home', pathlib.Path(tmp) / 'units').returncode, 0)

    def test_existing_configs_units_and_dropins_preserved(self):
        for name in ['.hermes/.env', '.hermes/config.yaml', '.hermes-web-ui',
                     'hermes-web-ui.service', 'hermes-web-ui.service.d',
                     'hermes-gateway.service', 'hermes-gateway.service.d']:
            with self.subTest(path=name), tempfile.TemporaryDirectory() as tmp:
                home, units = pathlib.Path(tmp) / 'home', pathlib.Path(tmp) / 'units'
                p = (home if name.startswith('.') else units) / name
                p.parent.mkdir(parents=True)
                p.write_bytes(b'keep-existing-content')
                self.assertNotEqual(fresh(home, units).returncode, 0)
                self.assertEqual(p.read_bytes(), b'keep-existing-content')

    def test_broken_symlinks_and_parent_symlink_refused(self):
        for name in ['.hermes', '.hermes/.env', '.hermes/config.yaml', '.hermes-web-ui',
                     'hermes-gateway.service', 'hermes-web-ui.service']:
            with self.subTest(path=name), tempfile.TemporaryDirectory() as tmp:
                home, units = pathlib.Path(tmp) / 'home', pathlib.Path(tmp) / 'units'
                p = (home if name.startswith('.') else units) / name
                p.parent.mkdir(parents=True)
                target = pathlib.Path(tmp) / 'missing-target'
                p.symlink_to(target)
                self.assertNotEqual(fresh(home, units).returncode, 0)
                self.assertTrue(p.is_symlink())
                self.assertFalse(target.exists())

    def test_optional_telegram_and_valid_admin(self):
        self.assertEqual(config().returncode, 0)
        self.assertEqual(config(CFG_TG_TOKEN='TEST_BOT_TOKEN', CFG_TG_ADMIN='123456').returncode, 0)

    def test_telegram_requires_positive_numeric_admin(self):
        for admin in ['', '0', '-12', 'abc', '12 34', '01']:
            with self.subTest(admin=admin):
                self.assertNotEqual(config(CFG_TG_TOKEN='TEST_BOT_TOKEN', CFG_TG_ADMIN=admin).returncode, 0)

    def test_empty_key_and_multiline_fields_fail_without_echo(self):
        self.assertNotEqual(config(CFG_API_KEY='').returncode, 0)
        for key in ['CFG_MODEL', 'CFG_BASE_URL', 'CFG_API_KEY', 'CFG_TG_TOKEN', 'CFG_TG_ADMIN']:
            for sep in ['\n', '\r']:
                value = 'TEST_PRIVATE_VALUE' + sep + 'INJECTED_LINE'
                with self.subTest(key=key, sep=repr(sep)):
                    result = config(**{key: value})
                    self.assertNotEqual(result.returncode, 0)
                    self.assertNotIn('TEST_PRIVATE_VALUE', result.stdout + result.stderr)


class InstallerGatewayTests(unittest.TestCase):
    def run_gateway_stage(self, token, fail=False):
        # Execute the real registration stage with an isolated systemctl stand-in.
        stage = SOURCE.split('$SUDO systemctl daemon-reload', 1)[1].split('# 启动 Web UI', 1)[0]
        with tempfile.TemporaryDirectory() as tmp:
            stub = pathlib.Path(tmp) / 'systemctl'
            log = pathlib.Path(tmp) / 'calls'
            stub.write_text('#!/bin/bash\nprintf "%s\\n" "$*" >> "$CALL_LOG"\nexit "$CALL_EXIT"\n')
            stub.chmod(0o700)
            env = dict(os.environ, PATH=tmp + ':' + os.environ['PATH'],
                       CFG_TG_TOKEN=token, SUDO='', CALL_LOG=str(log), CALL_EXIT='17' if fail else '0')
            result = subprocess.run(['bash', '-euc', stage + '\necho STAGE_COMPLETE'],
                                    env=env, capture_output=True, text=True)
            return result, log.read_text().splitlines() if log.exists() else []

    def test_gateway_starts_with_and_without_telegram(self):
        for token in ['', 'TEST_BOT_TOKEN']:
            with self.subTest(telegram=bool(token)):
                result, calls = self.run_gateway_stage(token)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIn('enable --now hermes-gateway', calls)

    def test_failed_gateway_start_stops_installation(self):
        result, calls = self.run_gateway_stage('', fail=True)
        self.assertEqual(result.returncode, 17)
        self.assertNotIn('STAGE_COMPLETE', result.stdout)

    def test_boot_dependency_and_final_health_check_are_unconditional(self):
        unit = SOURCE.split('Description=Hermes Web UI Service', 1)[1].split('EOF', 1)[0]
        self.assertIn('Wants=network-online.target hermes-gateway.service', unit)
        final = SOURCE.split('$SUDO systemctl is-active --quiet hermes-web-ui', 1)[1].split('echo ""', 1)[0]
        with tempfile.TemporaryDirectory() as tmp:
            stub = pathlib.Path(tmp) / 'systemctl'
            stub.write_text('#!/bin/bash\nexit 19\n')
            stub.chmod(0o700)
            env = dict(os.environ, PATH=tmp + ':' + os.environ['PATH'], SUDO='', CFG_TG_TOKEN='')
            result = subprocess.run(['bash', '-euc', final + '\necho INSTALL_SUCCESS'],
                                    env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 19)
            self.assertNotIn('INSTALL_SUCCESS', result.stdout)


class InstallerPromptTests(unittest.TestCase):
    def run_prompt(self, name, call):
        return subprocess.run(['bash', '-euc', function(name) + '\n' + call],
                              stdin=subprocess.DEVNULL, capture_output=True, text=True,
                              start_new_session=True, timeout=5)

    def test_no_terminal_optional_prompt_uses_default(self):
        result = self.run_prompt('prompt_input', 'prompt_input optional "fallback" value; printf "%s" "$value"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'fallback')
        self.assertEqual(result.stderr, '')

    def test_no_terminal_missing_secret_reaches_config_validation(self):
        call = 'prompt_secret key CFG_API_KEY\n' + function('validate_installer_config') + '\nvalidate_installer_config'
        env = dict(os.environ, CFG_MODEL='test', CFG_BASE_URL='https://example.com', CFG_TG_TOKEN='', CFG_TG_ADMIN='')
        result = subprocess.run(['bash', '-euc', function('prompt_secret') + '\n' + call],
                                env=env, stdin=subprocess.DEVNULL, capture_output=True,
                                text=True, start_new_session=True, timeout=5)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('API Key 不能为空', result.stderr)
        self.assertNotIn('/dev/tty', result.stderr)

    def test_interactive_terminal_still_reads_input(self):
        import pty
        master, slave = pty.openpty()
        try:
            process = subprocess.Popen(['bash', '-euc', function('prompt_input') +
                                       '\nprompt_input model fallback value; printf "%s" "$value"'],
                                       stdin=slave, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            os.write(master, b'interactive-model\n')
            stdout, stderr = process.communicate(timeout=5)
            self.assertEqual(process.returncode, 0, stderr)
            self.assertEqual(stdout, b'interactive-model')
        finally:
            os.close(master)
            os.close(slave)


if __name__ == '__main__':
    unittest.main()
