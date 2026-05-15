import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from scripts.db_backup import backup_database, default_backup_path


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
            with patch("scripts.db_backup.subprocess.run") as run:
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


if __name__ == "__main__":
    unittest.main()
