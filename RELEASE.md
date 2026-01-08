# Release Script

Automated release process for magic-agent.

## Prerequisites

- `gh` CLI installed: `brew install gh`
- `committer` script installed (see [AGENTS.md](AGENTS.md))
- Homebrew repo at `~/Documents/projects/homebrew-magic-agent`
- Clean git working directory

## Usage

```bash
./release.sh
```

## What it does

1. **Checks preconditions**
   - Validates git status (must be clean)
   - Checks current branch
   - Verifies dependencies installed

2. **Version bump**
   - Prompts for new version (semver format)
   - Updates `Cargo.toml`
   - Commits changes

3. **Git operations**
   - Creates annotated tag
   - Pushes commits and tags to remote

4. **Build & package**
   - Builds release binary with `cargo build --release`
   - Creates tarball with binary + `resolve_bridge.py`
   - Calculates SHA256 checksum

5. **GitHub release**
   - Creates release via `gh release create`
   - Uploads tarball as asset
   - Attaches release notes

6. **Homebrew formula**
   - Pulls latest changes from homebrew repo
   - Updates version, URL, and SHA256
   - Commits and pushes formula update

## Interactive prompts

The script will ask for:
- New version number (e.g., `0.5.0`)
- Commit message (optional, defaults to "Release v{version}")
- Release notes (optional, defaults to auto-generated)

## Example output

```bash
$ ./release.sh

Checking git status...
Current version: 0.4.0

Enter new version (e.g., 0.5.0):
0.5.0

========================================
Release Summary:
  Current version: 0.4.0
  New version: 0.5.0
========================================
Proceed? (y/n) y

Step 1: Bumping version in Cargo.toml...
Step 2: Committing changes...
Step 3: Creating git tag...
Step 4: Pushing to remote...
Step 5: Building release binary...
Step 6: Creating tarball...
Step 7: Calculating SHA256...
SHA256: abc123...
Step 8: Creating GitHub release...
Release created: https://github.com/decocereus/magic-agent/releases/tag/v0.5.0
Step 9: Updating Homebrew formula...
Step 10: Committing and pushing Homebrew formula...

========================================
Release complete!
========================================
Version: 0.5.0
Release: https://github.com/decocereus/magic-agent/releases/tag/v0.5.0
Homebrew: Updated

To test release:
  brew update && brew reinstall magic-agent

To verify:
  magic-agent --version
```

## Rollback

If something goes wrong, you can rollback:

```bash
# Delete tag (local + remote)
git tag -d v0.5.0
git push origin :refs/tags/v0.5.0

# Delete release
gh release delete v0.5.0

# Reset Cargo.toml version
git checkout HEAD~1 -- Cargo.toml
```
