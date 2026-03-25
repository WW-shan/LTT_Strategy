import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
README_PATH = REPO_ROOT / "README.md"


class ReadmeDocumentationTests(unittest.TestCase):
    def test_readme_documents_runtime_data_model(self):
        readme = README_PATH.read_text(encoding="utf-8")

        self.assertIn("ClawCloud", readme)
        self.assertIn("/app/data", readme)
        self.assertIn("./data", readme)
        self.assertRegex(readme, r"(?i)worker|background service")

        project_structure_match = re.search(
            r"## 项目结构\n\n```text\n(?P<section>[\s\S]*?)\n```",
            readme,
        )
        self.assertIsNotNone(project_structure_match)
        project_structure = project_structure_match.group("section")

        self.assertIn("├── data/", project_structure)
        self.assertIn("│   ├── allowed_users.txt", project_structure)
        self.assertIn("│   ├── user_settings.json", project_structure)
        self.assertNotRegex(project_structure, re.compile(r"(?m)^├── allowed_users\.txt\b"))
        self.assertNotRegex(project_structure, re.compile(r"(?m)^├── user_settings\.json\b"))

    def test_readme_documents_legacy_user_settings_migration_caveat(self):
        readme = README_PATH.read_text(encoding="utf-8")

        self.assertIn("默认情况下，运行时文件位于 `data/` 下，而不是项目根目录。", readme)
        self.assertIn("为兼容旧版本升级", readme)
        self.assertIn("项目根目录下遗留的 `user_settings.json` 一次性迁移到 `data/user_settings.json`", readme)
        self.assertIn("迁移完成后，程序始终以数据目录中的 `user_settings.json` 为准", readme)
        self.assertIn("项目根目录下遗留的 `./user_settings.json` 一次性迁移到 `./data/user_settings.json`", readme)
        self.assertIn("迁移完成后，程序始终读取 `./data/user_settings.json`", readme)
        self.assertNotIn("临时回退读取", readme)


if __name__ == "__main__":
    unittest.main()
