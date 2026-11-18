"""Create a clean source package from an explicit allowlist, never from local runs."""
import argparse
from pathlib import Path
import shutil
import zipfile

ROOT=Path(__file__).resolve().parents[1]
FILES=[
    "README.md","README.zh-CN.md","LICENSE","CONTRIBUTING.md","SECURITY.md","CHANGELOG.md",
    ".gitignore",".gitattributes","打开修订室.cmd","launch.py","server.py","engine.py","providers.py","review_schema.json",
    "web/index.html","web/app.js","web/style.css","web/favicon.svg",
    "web/demo/scene.html","web/demo/report.json","web/demo/hud.png","web/demo/inventory.png",
    "docs/index.html","docs/assets/review.png","docs/providers.md","docs/adapters.md","docs/validation.md",
    "tests/test_review.py","tests/test_providers.py","tests/serve_fixture.py",
    "tools/build_demo.py","tools/package_release.py","tools/build_windows.py","tools/windows-runtime.json",
    "webplay.py","requirements-web.txt","web/demo/practice.js","tests/test_webplay.py","docs/web-routes.md",
    ".github/workflows/tests.yml",".github/ISSUE_TEMPLATE/bug_report.md",".github/ISSUE_TEMPLATE/feature_request.md",
]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination",type=Path,help="A new, empty destination path; existing folders are never replaced")
    args=parser.parse_args()
    target=args.destination.resolve()
    archive=target.parent/(target.name+".zip")
    if target.exists() or archive.exists():
        parser.error("Destination or ZIP already exists; choose a new name to preserve existing work.")
    for name in FILES:
        if not (ROOT/name).is_file(): parser.error("Missing release source: "+name)
    target.mkdir(parents=True)
    for name in FILES:
        destination=target/name
        destination.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(ROOT/name,destination)
    with zipfile.ZipFile(archive,"w",zipfile.ZIP_DEFLATED) as bundle:
        for name in FILES: bundle.write(target/name,target.name+"/"+name)
    print(f"Prepared {len(FILES)} source files: {target}")
    print(f"Archive: {archive}")


if __name__=="__main__":main()
