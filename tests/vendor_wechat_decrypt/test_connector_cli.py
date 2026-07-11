import io
import json
import os
import sys
import tempfile
import unittest
from unittest.mock import patch


class ConnectorCliTests(unittest.TestCase):
    def test_detect_outputs_json(self):
        import connector_cli

        stdout = io.StringIO()
        with patch("connector_runtime.detect_connector", return_value={
            "ok": True,
            "connector": "wechat",
            "action": "detect",
            "error_code": None,
            "db_dir": r"C:\中文 路径\db_storage",
        }):
            code = connector_cli.main(["wechat", "detect", "--json"], stdout=stdout)

        self.assertEqual(code, 0)
        payload = json.loads(stdout.getvalue())
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["db_dir"], r"C:\中文 路径\db_storage")

    def test_extract_key_rejects_relative_runtime_dir(self):
        import connector_cli

        stdout = io.StringIO()
        code = connector_cli.main(
            ["wechat", "extract-key", "--runtime-dir", "relative-path", "--json"],
            stdout=stdout,
        )

        self.assertEqual(code, 1)
        payload = json.loads(stdout.getvalue())
        self.assertEqual(payload["error_code"], "INVALID_RUNTIME_DIR")

    def test_extract_key_passes_absolute_runtime_dir(self):
        import connector_cli

        with tempfile.TemporaryDirectory() as runtime_dir:
            stdout = io.StringIO()
            captured = {}

            def fake_extract(connector, path):
                captured["connector"] = connector
                captured["path"] = path
                return {
                    "ok": True,
                    "connector": connector,
                    "action": "extract-key",
                    "error_code": None,
                }

            with patch("connector_runtime.extract_key", side_effect=fake_extract):
                code = connector_cli.main(
                    ["wxwork", "extract-key", "--runtime-dir", runtime_dir, "--json"],
                    stdout=stdout,
                )

        self.assertEqual(code, 0)
        self.assertEqual(captured["connector"], "wxwork")
        self.assertTrue(os.path.isabs(captured["path"]))


class ConnectorRuntimeTests(unittest.TestCase):
    def test_detect_wechat_db_dir_prefers_latest_utf8_candidate(self):
        import connector_runtime

        with tempfile.TemporaryDirectory() as temp_dir:
            config_dir = os.path.join(temp_dir, "config")
            os.makedirs(config_dir)
            root = os.path.join(temp_dir, "root 目录")
            old_dir = os.path.join(root, "xwechat_files", "wxid_old", "db_storage")
            new_dir = os.path.join(root, "xwechat_files", "wxid_new", "db_storage")
            os.makedirs(old_dir)
            os.makedirs(new_dir)
            ini_path = os.path.join(config_dir, "acct.ini")
            with open(ini_path, "w", encoding="utf-8") as f:
                f.write(root)
            os.utime(old_dir, (1, 1))
            os.utime(new_dir, None)

            selected = connector_runtime.detect_wechat_db_dir_from_ini(config_dir)

        self.assertEqual(selected, new_dir)

    def test_build_runtime_config_is_connector_isolated(self):
        import connector_runtime

        with tempfile.TemporaryDirectory() as runtime_dir:
            wechat_cfg = connector_runtime.build_runtime_config(
                "wechat",
                runtime_dir,
                r"C:\data\wechat\db_storage",
            )
            wxwork_cfg = connector_runtime.build_runtime_config(
                "wxwork",
                runtime_dir,
                r"C:\data\wxwork\Data",
            )

        self.assertTrue(wechat_cfg["keys_file"].endswith(os.path.join("secrets", "all_keys.json")))
        self.assertTrue(wxwork_cfg["keys_file"].endswith(os.path.join("secrets", "wxwork_keys.json")))
        self.assertNotEqual(wechat_cfg["keys_file"], wxwork_cfg["keys_file"])

    def test_extract_key_failure_does_not_expose_secret_stdout(self):
        import connector_runtime

        with tempfile.TemporaryDirectory() as runtime_dir:
            with patch("connector_runtime.detect_connector", return_value={
                "ok": True,
                "connector": "wechat",
                "action": "detect",
                "error_code": None,
                "db_dir": r"C:\db_storage",
            }), patch("connector_runtime.run_managed_script", return_value={
                "returncode": 1,
                "stdout": "enc_key=abcdef0123456789",
                "stderr": "",
            }):
                result = connector_runtime.extract_key("wechat", runtime_dir)

        self.assertFalse(result["ok"])
        self.assertEqual(result["error_code"], "KEY_EXTRACTION_FAILED")
        self.assertNotIn("abcdef0123456789", json.dumps(result, ensure_ascii=False))

    def test_detect_wxwork_suppresses_helper_stdout(self):
        import connector_runtime

        class FakeWxworkModule:
            @staticmethod
            def auto_detect_wxwork_db_dir():
                print("this should not reach stdout")
                return r"C:\WXWork\Data"

        with patch("connector_runtime.is_windows", return_value=True), patch(
            "connector_runtime.is_process_running", return_value=True
        ), patch("os.path.isdir", return_value=True), patch.dict(
            sys.modules,
            {"find_wxwork_keys": FakeWxworkModule},
        ):
            stdout = io.StringIO()
            with patch("sys.stdout", stdout):
                result = connector_runtime.detect_connector("wxwork")

        self.assertTrue(result["ok"])
        self.assertEqual(stdout.getvalue(), "")


if __name__ == "__main__":
    unittest.main()
