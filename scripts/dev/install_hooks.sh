#!/bin/bash
set -e
echo "Installing pre-commit hooks..."
pre-commit install
echo "Installing post-commit hook..."
cp scripts/dev/post_commit_hook.sh .git/hooks/post-commit
chmod +x .git/hooks/post-commit
echo "Done. Run 'make ci' to verify everything is wired."
