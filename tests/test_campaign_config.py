import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from raglib import campaign
from scripts.campaign import init_campaign


class CampaignConfigTest(unittest.TestCase):
    def test_campaign_root_uses_active_campaign_name(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict("os.environ", {"FARRLIND_CAMPAIGNS_ROOT": tmp, "FARRLIND_CAMPAIGN": "new table"}):
            self.assertEqual(campaign.active_campaign_name(), "new_table")
            self.assertEqual(campaign.campaign_root(), Path(tmp).resolve() / "new_table")

    def test_campaign_database_url_uses_campaign_metadata(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict("os.environ", {"FARRLIND_CAMPAIGNS_ROOT": tmp, "FARRLIND_CAMPAIGN": "shadow"}):
            root = campaign.campaign_root()
            root.mkdir(parents=True)
            (root / "campaign.yaml").write_text(
                "database:\n  name: shadow_db\n  user: keeper\n  password: secret\n  port: 5544\n",
                encoding="utf-8",
            )

            self.assertEqual(
                campaign.campaign_database_url(host="db"),
                "postgresql+psycopg2://keeper:secret@db:5544/shadow_db",
            )

    def test_init_campaign_creates_standard_folders_and_metadata(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict("os.environ", {"FARRLIND_CAMPAIGNS_ROOT": tmp}):
            root = init_campaign("Shadowed Isles", "Shadowed Isles")

            self.assertTrue((root / "campaign.yaml").exists())
            self.assertTrue((root / "audio").is_dir())
            self.assertTrue((root / "raw").is_dir())
            self.assertTrue((root / "extracted").is_dir())
            self.assertTrue((root / "assets").is_dir())
            self.assertIn("id: shadowed_isles", (root / "campaign.yaml").read_text(encoding="utf-8"))
            self.assertFalse(campaign.campaign_feature_enabled("songbook", campaign_name="shadowed_isles", default=True))


if __name__ == "__main__":
    unittest.main()
