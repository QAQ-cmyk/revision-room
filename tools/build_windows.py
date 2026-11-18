"""Build a portable Windows x64 bundle from audited source paths and locked redistributables."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import urllib.request
import zipfile

from package_release import FILES, ROOT


def dependency(record, cache):
    path = cache / record["filename"]
    if not path.exists():
        with urllib.request.urlopen(record["url"], timeout=90) as src, path.open("wb") as dest:
            shutil.copyfileobj(src, dest)
    if hashlib.sha256(path.read_bytes()).hexdigest() != record["sha256"]:
        raise ValueError(f"Checksum mismatch: {path.name}")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cache", type=Path, default=ROOT / "dist" / "cache")
    args = parser.parse_args()
    output = args.output.resolve()
    args.cache.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    lock = json.loads((ROOT / "tools/windows-runtime.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(dir=output.parent) as stage:
        root = Path(stage) / "revision-room"
        for name in FILES:
            dest = root / name
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, dest)
        runtime = root / "runtime"
        for record in lock:
            archive = dependency(record, args.cache)
            with zipfile.ZipFile(archive) as z:
                target = runtime if archive.suffix == ".zip" else runtime / "Lib/site-packages"
                z.extractall(target)
        path_config, = runtime.glob("python*._pth")
        stdlib, = runtime.glob("python*.zip")
        path_config.write_text(stdlib.name+"\n.\n..\nLib/site-packages\n", encoding="ascii")
        temp_zip = Path(stage) / "product.zip"
        with zipfile.ZipFile(temp_zip, "w", zipfile.ZIP_DEFLATED, compresslevel=5) as product:
            for item in sorted(root.rglob("*")):
                if item.is_file():
                    product.write(item, item.relative_to(root.parent))
        temp_zip.replace(output)
    print(output)


if __name__ == "__main__":
    main()
