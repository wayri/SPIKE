"""Download pinned public PCB data for local validation; never execute it."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "build/public-board-corpus"
REPOS = ["KiCad/kicad-source-mirror", "OLIMEX/OLINUXINO", "beagleboard/beaglebone-black",
         "sjgallagher2/ODBplusplus-Parser", "FixturFab/ODB2kicad", "mcix/odbpp"]

def get(url, limit=128 * 1024 * 1024):
    req = urllib.request.Request(url, headers={"User-Agent": "SPIKE-public-corpus-validation"})
    with urllib.request.urlopen(req, timeout=60) as response:
        data = response.read(limit + 1)
    if len(data) > limit: raise ValueError("Download exceeds corpus member limit")
    return data

def discover(repos=None):
    DEST.mkdir(parents=True, exist_ok=True)
    previous = DEST / "discovery.json"
    output = json.loads(previous.read_text()) if repos and previous.exists() else []
    for repo in repos or REPOS:
        try:
            info = json.loads(get(f"https://api.github.com/repos/{repo}"))
            branch = info["default_branch"]
            commit = json.loads(get(f"https://api.github.com/repos/{repo}/commits/{branch}"))["sha"]
            tree = json.loads(get(f"https://api.github.com/repos/{repo}/git/trees/{commit}?recursive=1"))
            tree_path = DEST / "trees" / (repo.replace("/", "__") + ".json")
            tree_path.parent.mkdir(parents=True, exist_ok=True)
            tree_path.write_text(json.dumps(tree), encoding="utf-8")
            entries = [e for e in tree["tree"] if e["type"] == "blob" and
                       (e["path"].lower().endswith((".kicad_pcb", ".tgz", ".tar.gz", ".zip")) or
                        "license" in e["path"].lower() or e["path"].lower().endswith(("readme.md", "copying")))]
            row = {"repository": repo, "commit": commit, "license": info.get("license"),
                   "tree_truncated": tree.get("truncated"), "entries": entries}
            output = [r for r in output if r["repository"] != repo] + [row]
            print(repo, commit, "candidates", len(entries), flush=True)
        except Exception as exc:
            output.append({"repository": repo, "error": str(exc)})
            print(repo, str(exc), flush=True)
    (DEST / "discovery.json").write_text(json.dumps(output, indent=2), encoding="utf-8")

def download(manifest):
    data = json.loads(Path(manifest).read_text(encoding="utf-8"))
    def fetch(pair):
        entry, item = pair
        folder = DEST / "sources" / entry["id"]
        folder.mkdir(parents=True, exist_ok=True)
        relative = Path(item["path"])
        if relative.is_absolute() or ".." in relative.parts: raise ValueError("Unsafe corpus path")
        url = f"https://raw.githubusercontent.com/{entry['repository']}/{entry['commit']}/" + urllib.parse.quote(item["path"])
        target = folder / relative
        expected = item.get("sha256")
        payload = target.read_bytes() if target.is_file() else get(url)
        digest = hashlib.sha256(payload).hexdigest()
        if expected and digest != expected: raise ValueError("Corpus hash mismatch")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)
        item.update(url=url, sha256=digest, bytes=len(payload), local_path=target.relative_to(ROOT).as_posix())
        print(entry["id"], relative, len(payload), flush=True)
    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(fetch, [(e, f) for e in data["sources"] for f in e["files"]]))
    Path(manifest).write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--discover", action="store_true")
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--repository", action="append")
    args = parser.parse_args()
    if args.discover: discover(args.repository)
    elif args.manifest: download(args.manifest)
    else: parser.error("Choose --discover or --manifest")
