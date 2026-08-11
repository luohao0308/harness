#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

bump="${1:-patch}"
case "$bump" in
  major|minor|patch) ;;
  v*) next_version="${bump#v}" ;;
  *)
    echo "usage: scripts/release.sh [major|minor|patch|vX.Y.Z]" >&2
    exit 1
    ;;
esac

current_version="$(
  python3 - <<'PY'
import json, pathlib
data = json.loads(pathlib.Path("apps/agent-console/package.json").read_text())
print(data["version"])
PY
)"

if [[ -z "${next_version:-}" ]]; then
  IFS=. read -r major minor patch <<<"$current_version"
  case "$bump" in
    major) major=$((major + 1)); minor=0; patch=0 ;;
    minor) minor=$((minor + 1)); patch=0 ;;
    patch) patch=$((patch + 1)) ;;
  esac
  next_version="$major.$minor.$patch"
fi

python3 - "$next_version" <<'PY'
import json, pathlib, re, sys
version = sys.argv[1]

def update_node_package(package_path: pathlib.Path) -> None:
    package_lock_path = package_path.with_name("package-lock.json")
    package = json.loads(package_path.read_text())
    package["version"] = version
    package_path.write_text(json.dumps(package, indent=2) + "\n")
    if package_lock_path.exists():
        lock = json.loads(package_lock_path.read_text())
        lock["version"] = version
        if "packages" in lock and "" in lock["packages"]:
            lock["packages"][""]["version"] = version
        package_lock_path.write_text(json.dumps(lock, indent=2) + "\n")

for package_path in (
    pathlib.Path("apps/agent-console/package.json"),
    pathlib.Path("apps/desktop-app/package.json"),
):
    update_node_package(package_path)

pyproject_path = pathlib.Path("services/api-server/pyproject.toml")
pyproject = pyproject_path.read_text()
pyproject = re.sub(r'^version = "[^"]+"', f'version = "{version}"', pyproject, count=1, flags=re.M)
pyproject_path.write_text(pyproject)
PY

tag="v$next_version"
echo "Prepared release $tag"
echo "Run validation, commit the version bump, then:"
echo "  git tag -a $tag -m \"Release $tag\""
echo "  git push origin HEAD --tags"
