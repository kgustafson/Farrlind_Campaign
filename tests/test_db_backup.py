import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from scripts.db_backup import backup_database, default_backup_path, pg_dump_url, sanitize_backup_file


class DatabaseBackupTest(unittest.TestCase):
    def test_default_backup_path_uses_timestamp(self):
        backup_path = default_backup_path(
            Path("/tmp/farrlind-backups"),
            datetime(2026, 5, 15, 1, 2, 3),
        )

        self.assertEqual(
            backup_path,
            Path("/tmp/farrlind-backups/farrlind_20260515_010203.sql"),
        )

    def test_backup_database_runs_pg_dump_with_clean_flags(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "backup.sql"
            with patch.dict("scripts.db_backup.os.environ", {}, clear=True), \
                 patch("scripts.db_backup.subprocess.run") as run:
                backup_path = backup_database(
                    output_path,
                    container="test_db",
                    user="test_user",
                    database="test_database",
                )

        self.assertEqual(backup_path, output_path)
        self.assertEqual(
            run.call_args.args[0],
            [
                "docker",
                "exec",
                "test_db",
                "pg_dump",
                "--clean",
                "--if-exists",
                "-U",
                "test_user",
                "-d",
                "test_database",
            ],
        )
        self.assertTrue(run.call_args.kwargs["check"])
        self.assertIsNotNone(run.call_args.kwargs["stdout"])

    def test_backup_database_uses_database_url_when_pg_dump_is_available(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            output_path = Path(tmp_dir) / "backup.sql"
            with patch.dict("scripts.db_backup.os.environ", {"FARRLIND_DATABASE_URL": "postgresql+psycopg2://user:pass@db:5432/farrlind"}), \
                 patch("scripts.db_backup.shutil.which", return_value="/usr/bin/pg_dump"), \
                 patch("scripts.db_backup.subprocess.run") as run:
                backup_path = backup_database(output_path)

        self.assertEqual(backup_path, output_path)
        self.assertEqual(
            run.call_args.args[0],
            [
                "pg_dump",
                "--clean",
                "--if-exists",
                "postgresql://user:pass@db:5432/farrlind",
            ],
        )

    def test_pg_dump_url_normalizes_sqlalchemy_scheme(self):
        self.assertEqual(
            pg_dump_url("postgresql+psycopg2://user:pass@db:5432/farrlind"),
            "postgresql://user:pass@db:5432/farrlind",
        )

    def test_sanitize_backup_file_removes_pg17_transaction_timeout(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            backup_path = Path(tmp_dir) / "backup.sql"
            backup_path.write_text(
                "SET statement_timeout = 0;\n"
                "SET transaction_timeout = 0;\n"
                "CREATE TABLE public.session (id integer);\n",
                encoding="utf-8",
            )

            sanitize_backup_file(backup_path)
            sanitized = backup_path.read_text(encoding="utf-8")

        self.assertEqual(
            sanitized,
            "SET statement_timeout = 0;\n"
            "CREATE TABLE public.session (id integer);\n",
        )


if __name__ == "__main__":
    unittest.main()
