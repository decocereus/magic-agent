#!/bin/bash

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Paths
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOMEBREW_REPO="$HOME/Documents/projects/homebrew-magic-agent"

# Check if we're in the right directory
if [ ! -f "$PROJECT_ROOT/Cargo.toml" ]; then
    echo -e "${RED}Error: Cargo.toml not found. Run this script from the project root.${NC}"
    exit 1
fi

# Check if Homebrew repo exists
if [ ! -d "$HOMEBREW_REPO/Formula" ]; then
    echo -e "${RED}Error: Homebrew repo not found at $HOMEBREW_REPO${NC}"
    exit 1
fi

# Check if gh CLI is installed
if ! command -v gh &> /dev/null; then
    echo -e "${RED}Error: gh CLI is not installed. Install it with: brew install gh${NC}"
    exit 1
fi

# Check if committer exists
if ! command -v committer &> /dev/null; then
    echo -e "${RED}Error: committer not found. Install it from AGENTS.md instructions.${NC}"
    exit 1
fi

# Check git status
echo -e "${BLUE}Checking git status...${NC}"
if [ -n "$(git status --porcelain)" ]; then
    echo -e "${RED}Error: Working directory has uncommitted changes.${NC}"
    git status
    exit 1
fi

# Check current branch
CURRENT_BRANCH=$(git branch --show-current)
if [ "$CURRENT_BRANCH" != "main" ]; then
    echo -e "${YELLOW}Warning: Not on main branch (current: $CURRENT_BRANCH)${NC}"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Get current version
CURRENT_VERSION=$(grep "^version" "$PROJECT_ROOT/Cargo.toml" | head -1 | sed 's/version = "\(.*\)"/\1/')
echo -e "${GREEN}Current version: $CURRENT_VERSION${NC}"

# Ask for new version
echo -e "${BLUE}Enter new version (e.g., 0.5.0):${NC}"
read -r NEW_VERSION

# Validate version format
if [[ ! $NEW_VERSION =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo -e "${RED}Error: Invalid version format. Use semver (e.g., 0.5.0)${NC}"
    exit 1
fi

# Confirm
echo -e "${YELLOW}========================================${NC}"
echo -e "${YELLOW}Release Summary:${NC}"
echo -e "  Current version: $CURRENT_VERSION"
echo -e "  New version: $NEW_VERSION"
echo -e "${YELLOW}========================================${NC}"
echo -ne "${YELLOW}Proceed? (y/n) "
read -r -n 1 -p ""
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo -e "${RED}Aborted${NC}"
    exit 1
fi

# Step 1: Bump version
echo -e "${BLUE}Step 1: Bumping version in Cargo.toml...${NC}"
sed -i '' "s/^version = \"$CURRENT_VERSION\"/version = \"$NEW_VERSION\"/" "$PROJECT_ROOT/Cargo.toml"

# Step 2: Commit changes
echo -e "${BLUE}Step 2: Committing changes...${NC}"
echo -ne "${YELLOW}Enter commit message (leave empty for default): "
read -r COMMIT_MSG

if [ -z "$COMMIT_MSG" ]; then
    COMMIT_MSG="Release v${NEW_VERSION}"
fi

~/.local/bin/committer "Release v${NEW_VERSION}" Cargo.toml

# Step 3: Create tag
echo -e "${BLUE}Step 3: Creating git tag...${NC}"
git tag -a "v${NEW_VERSION}" -m "Release v${NEW_VERSION}"

# Step 4: Push to remote
echo -e "${BLUE}Step 4: Pushing to remote...${NC}"
git push origin main
git push origin "v${NEW_VERSION}"

# Step 5: Build release
echo -e "${BLUE}Step 5: Building release binary...${NC}"
cargo build --release

# Step 6: Create tarball
echo -e "${BLUE}Step 6: Creating tarball...${NC}"
TEMP_DIR="/tmp/magic-agent-v${NEW_VERSION}"
TARBALL="/tmp/magic-agent-v${NEW_VERSION}-macos.tar.gz"

rm -rf "$TEMP_DIR"
mkdir -p "$TEMP_DIR"
cp "$PROJECT_ROOT/target/release/magic-agent" "$TEMP_DIR/"
cp "$PROJECT_ROOT/python/resolve_bridge.py" "$TEMP_DIR/"
# Create flat tarball (no directory wrapper)
tar -czf "$TARBALL" -C "$TEMP_DIR" .

# Step 7: Calculate SHA256
echo -e "${BLUE}Step 7: Calculating SHA256...${NC}"
SHA256=$(shasum -a 256 "$TARBALL" | cut -d' ' -f1)
echo -e "${GREEN}SHA256: $SHA256${NC}"

# Step 8: Create GitHub release
echo -e "${BLUE}Step 8: Creating GitHub release...${NC}"
echo -ne "${YELLOW}Enter release notes (or leave empty for auto-generated): "
read -r RELEASE_NOTES

if [ -z "$RELEASE_NOTES" ]; then
    RELEASE_NOTES="## What's New\n\nSee commit history for details."
fi

gh release create "v${NEW_VERSION}" "$TARBALL" \
  --title "v${NEW_VERSION}" \
  --notes "$RELEASE_NOTES"

RELEASE_URL=$(gh release view "v${NEW_VERSION}" --json url --jq '.url')
echo -e "${GREEN}Release created: $RELEASE_URL${NC}"

# Step 9: Update Homebrew formula
echo -e "${BLUE}Step 9: Updating Homebrew formula...${NC}"
cd "$HOMEBREW_REPO" || exit 1

# Pull latest changes
echo -e "${BLUE}Pulling latest Homebrew changes...${NC}"
git pull origin main --rebase || {
    echo -e "${RED}Failed to pull. Checking for conflicts...${NC}"
    if [ -n "$(git status --porcelain)" ]; then
        echo -e "${RED}Merge conflicts detected. Please resolve manually.${NC}"
        exit 1
    fi
}

# Update formula
sed -i '' "s|url \".*magic-agent-v[^\"]*\"|url \"https://github.com/decocereus/magic-agent/releases/download/v${NEW_VERSION}/magic-agent-v${NEW_VERSION}-macos.tar.gz\"|" Formula/magic-agent.rb
sed -i '' "s/sha256 \"[^\"]*\"/sha256 \"$SHA256\"/" Formula/magic-agent.rb
sed -i '' "s/version \"[^\"]*\"/version \"$NEW_VERSION\"/" Formula/magic-agent.rb

# Step 10: Commit and push Homebrew formula
echo -e "${BLUE}Step 10: Committing and pushing Homebrew formula...${NC}"
~/.local/bin/committer "Update magic-agent to v${NEW_VERSION}" Formula/magic-agent.rb
git push origin main

# Done
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Release complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo -e "Version: ${NEW_VERSION}"
echo -e "Release: $RELEASE_URL"
echo -e "Homebrew: Updated"
echo -e ""
echo -e "${BLUE}To test the release:${NC}"
echo -e "  brew update && brew reinstall magic-agent"
echo -e ""
echo -e "${BLUE}To verify:${NC}"
echo -e "  magic-agent --version"
