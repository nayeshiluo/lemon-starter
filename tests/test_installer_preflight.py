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


if __name__ == '__main__':
    unittest.main()
