#!/usr/bin/env bash
set -euo pipefail

VERSION="${1:-}"

if [[ -z "$VERSION" ]]; then
    echo "Usage: make version VERSION=X.Y.Z"
    exit 1
fi

if [[ ! "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+(-[0-9A-Za-z.-]+)?$ ]]; then
    echo "Error: Invalid semantic version format: $VERSION"
    exit 1
fi

TAG="v$VERSION"
PYPROJECT="pyproject.toml"
CHANGELOG="CHANGELOG.md"

if git rev-parse "$TAG" >/dev/null 2>&1; then
    echo "Error: Tag $TAG already exists"
    exit 1
fi

echo "Preparing release $TAG..."

sed -i "0,/^version = \".*\"/{s/^version = \".*\"/version = \"$VERSION\"/}" "$PYPROJECT"

uvx git-cliff --tag "$TAG" -o "$CHANGELOG"

git add "$PYPROJECT" "$CHANGELOG"

git commit -m "chore(release): $TAG"

git tag -a "$TAG" -m "Release $TAG"

echo "Release $TAG created successfully."
echo ""
git log --oneline -1
git tag -n1 "$TAG"

PUSH_PROMPT="\nPush to remote? [y/N] "
if [[ -t 1 ]]; then
    read -p "$PUSH_PROMPT" -n 1 -r
    echo ""
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        git push
        git push --tags
        echo "Pushed to remote."
    else
        echo "Not pushed. Push manually with:"
        echo "  git push"
        echo "  git push --tags"
    fi
else
    echo -e "$PUSH_PROMPT"
    echo "Not pushed. Push manually with:"
    echo "  git push"
    echo "  git push --tags"
fi