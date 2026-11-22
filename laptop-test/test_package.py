from pathlib import Path
import tempfile
import unittest
import zipfile
from build_package import build


class PackageTest(unittest.TestCase):
    def test_credentials_results_and_environment_excluded(self):
        parent=Path(__file__).resolve().parent / "results"
        parent.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(dir=parent) as temporary:
            root=Path(temporary)/"source"
            root.mkdir()
            for relative in ("config.json","camera.example.json","camera.local.json","faces.local.json","telegram.local.json",
                             "results/summary.json",".venv/private.py","models/model.task","app.py","phone_remote.html",
                             "web_console.html","web_console.css","web_console.js"):
                path=root/relative
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text("fixture")
            target=Path(temporary)/"package.zip"
            members=build(root,target)
            self.assertEqual(set(members),{"laptop-test/config.json","laptop-test/camera.example.json",
                                          "laptop-test/app.py","laptop-test/phone_remote.html",
                                          "laptop-test/web_console.html","laptop-test/web_console.css","laptop-test/web_console.js"})
            with zipfile.ZipFile(target) as archive:
                self.assertIsNone(archive.testzip())


if __name__ == "__main__":
    unittest.main()
