"""Build a shareable ZIP without environments, results or camera secrets."""
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parent


def build(root=ROOT, destination=None):
    root = Path(root)
    destination = Path(destination) if destination else root.parent / "laptop-test-package.zip"
    allowed = {".py", ".bat", ".md", ".txt", ".json", ".html", ".css", ".js"}
    excluded = {".venv", "venv", "__pycache__", "results", ".git"}
    members = []
    with zipfile.ZipFile(destination,"w",zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root)
            if (not path.is_file() or any(part in excluded for part in relative.parts)
                or path.suffix not in allowed or path.name.endswith(".local.json")
                or path.name.startswith(".env")):
                continue
            name = "laptop-test/" + relative.as_posix()
            archive.write(path,name)
            members.append(name)
    with zipfile.ZipFile(destination) as archive:
        if archive.testzip() is not None:
            raise RuntimeError("ZIP integrity check failed")
    return members


if __name__ == "__main__":
    members=build()
    print("Package verified:",len(members),"files; local credentials and results excluded.")
