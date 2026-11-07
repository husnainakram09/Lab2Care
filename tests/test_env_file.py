"""Tests for loading local settings from a .env file."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from api.env_file import load_env_file


class TestEnvFile(unittest.TestCase):

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / ".env"

        self.environment = patch.dict(os.environ, {}, clear=False)
        self.environment.start()

        for name in ("LAB2CARE_A", "LAB2CARE_B", "LAB2CARE_C",
                     "LAB2CARE_EMPTY", "LAB2CARE_SET"):
            os.environ.pop(name, None)

    def tearDown(self):
        self.environment.stop()
        self.temp.cleanup()

    def write(self, text, encoding="utf-8"):
        self.path.write_text(text, encoding=encoding)

    def test_parses_values_comments_quotes_and_export(self):
        self.write(
            "# comment\n"
            "\n"
            "LAB2CARE_A=plain\n"
            "export LAB2CARE_B = \"quoted value\"\n"
            "LAB2CARE_C='has=equals'\n"
        )

        loaded = load_env_file(self.path)

        self.assertEqual(
            loaded, ["LAB2CARE_A", "LAB2CARE_B", "LAB2CARE_C"]
        )
        self.assertEqual(os.environ["LAB2CARE_A"], "plain")
        self.assertEqual(os.environ["LAB2CARE_B"], "quoted value")
        self.assertEqual(os.environ["LAB2CARE_C"], "has=equals")

    def test_existing_environment_wins(self):
        os.environ["LAB2CARE_SET"] = "from-service"
        self.write("LAB2CARE_SET=from-file\n")

        self.assertEqual(load_env_file(self.path), [])
        self.assertEqual(os.environ["LAB2CARE_SET"], "from-service")

    def test_empty_value_stays_unconfigured(self):
        self.write("LAB2CARE_EMPTY=\n")

        load_env_file(self.path)

        self.assertNotIn("LAB2CARE_EMPTY", os.environ)

    def test_notepad_byte_order_mark_is_accepted(self):
        self.write("LAB2CARE_A=value\n", encoding="utf-8-sig")

        self.assertEqual(load_env_file(self.path), ["LAB2CARE_A"])

    def test_malformed_line_error_does_not_reveal_value(self):
        self.write("this is secret-key-material\n")

        with self.assertRaises(ValueError) as raised:
            load_env_file(self.path)

        self.assertIn("line 1", str(raised.exception))
        self.assertNotIn("secret", str(raised.exception))

    def test_missing_file_is_ignored(self):
        self.assertEqual(load_env_file(self.path.with_name("none")), [])


if __name__ == "__main__":
    unittest.main()
