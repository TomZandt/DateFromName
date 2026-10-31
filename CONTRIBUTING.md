# Contributing

Start with the [README](README.md), then the
[developer guide](docs/DEVELOPMENT.md) for running from source, testing and
releasing. This page covers how to write commit messages and how version
numbers are chosen. The two are linked: the commit types decide the next
version.

## Commit messages: Conventional Commits

Every commit message follows [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/).
Commits up to v1.2.0 came before this rule and keep their original messages,
because published history isn't rewritten.

```
<type>(<optional scope>): <summary>
```

In full:

```
<type>(<optional scope>): <summary>

<optional body: what changed and why>

<optional footer, e.g. BREAKING CHANGE: ... or Co-Authored-By: ...>
```

- **Summary:** imperative and lower case, no full stop, about 72 characters
  at most. For example, "add renumber tab", not "Added the renumber tab."
- **Body:** say *why*, not just what. Wrap at about 72 characters.
- **Breaking change:** put `!` after the type or scope (`feat(organise)!: …`)
  and explain it in a `BREAKING CHANGE:` footer. For this app, that means
  anything that would surprise existing users, such as changing the
  `YYYY_MM_DD_####_` format or how month folders are named.

### Types

| Type | Use for | Version bump |
| ---- | ------- | ------------ |
| `feat` | Something new a user can see or use | minor (1.**3**.0) |
| `fix` | A bug fix a user would notice | patch (1.3.**1**) |
| `docs` | README, guides, changelog, comments only | none |
| `test` | Adding or changing tests only | none |
| `refactor` | Code changes that don't change behaviour | none |
| `perf` | Faster, same behaviour | patch |
| `build` | Dependencies, PyInstaller, requirements files | none |
| `ci` | GitHub Actions workflows | none |
| `chore` | Anything else (e.g. `.gitignore`) | none |

A breaking change bumps the major version (**2**.0.0), whatever its type.

### Scopes

Optional, but use one when the change is about one area:

| Scope | Area |
| ----- | ---- |
| `fix-dates` | The Fix dates tab and the date rules (`plan_folder`, `_decide`, `apply_plan`) |
| `names` | Recognising file names (`PATTERNS`, `parse_name`) |
| `organise` | The Organise tab (`plan_organise`, `plan_new_paths`) |
| `renumber` | The Renumber tab (`plan_renumber`) |
| `ui` | The window in general (`app.py`) |
| `updater` | Self-update (`updater.py`) |
| `release` | The release workflow and versioning |

### Examples

```
feat(names): recognise OnePlus IMG20260822123456 names
fix(organise): don't nest month folders when a month folder is chosen
docs: make the README the single source of truth
test(updater): cover the swap and rollback
ci: run the tests on every push
feat(organise)!: number from 0001 instead of 0000

BREAKING CHANGE: existing prefixes are renumbered the next time Organise runs.
```

### Checking messages automatically

The repo includes a `commit-msg` hook that rejects messages that don't follow
this format. Turn it on once per clone:

```
git config core.hooksPath .githooks
```

Merge commits and `fixup!`/`squash!` commits are allowed through.

## Branches and pull requests

Small fixes can go straight to `main`. For anything bigger:

1. Branch from `main`, named after the commit type, e.g.
   `feat/heic-writing` or `fix/organise-clash`.
2. Commit in Conventional Commits style. Add a line under `## Unreleased` in
   [CHANGELOG.md](CHANGELOG.md) for anything users will notice.
3. Open a pull request. Its title should be a Conventional Commit too, because
   it becomes the commit message if you squash-merge. The Test workflow runs
   on it.
4. Merge when the tests pass, then follow
   [After merging a branch](docs/DEVELOPMENT.md#after-merging-a-branch).

## Versions: Semantic Versioning

Releases are numbered with [Semantic Versioning](https://semver.org/):
**MAJOR.MINOR.PATCH**, tagged as `vMAJOR.MINOR.PATCH` (e.g. `v1.3.0`).

| Part | Goes up when | Examples in this app | Then |
| ---- | ------------ | -------------------- | ---- |
| **MAJOR** | Something works differently in a way that could surprise someone who already uses it | Changing the `YYYY_MM_DD_####_` format or month folder names; changing which date wins in the Fix dates rules; removing a tab | MINOR and PATCH go back to 0 (1.4.2 → **2.0.0**) |
| **MINOR** | Something new is added and everything existing keeps working | A new tab or option, new file name formats, new file types | PATCH goes back to 0 (1.3.2 → 1.**4**.0) |
| **PATCH** | Only fixes: something that should already have worked now does | A wrong date, a crash, a misleading message | 1.3.0 → 1.3.**1** |

What counts as "the API" here is what users see: the app's behaviour, the
names and folders it creates, and the command-line options.

### Picking the next version

Look at the commits since the last release:

```
git log --oneline $(git describe --tags --abbrev=0)..HEAD
```

The highest-ranked commit wins:

1. Any `!` or `BREAKING CHANGE:` → **MAJOR**
2. Otherwise any `feat` → **MINOR**
3. Otherwise any `fix` or `perf` → **PATCH**
4. Only `docs`, `test`, `refactor`, `build`, `ci` or `chore` → **no release
   needed**. Users wouldn't notice anything, and a release would just make the
   update bar appear for nothing.

### Rules

- **Numbers only.** No `-beta` or `-rc1`. The app's updater compares versions
  as numbers and ignores anything else (see the
  [developer guide](docs/DEVELOPMENT.md#self-update)). Test pre-releases by
  building locally instead.
- **Always go up, never reuse.** Installed copies only offer a version higher
  than their own. A released tag is never moved or deleted. Fix mistakes with
  a new PATCH release.
- **Each part counts on its own:** `v1.10.0` comes after `v1.9.0`.
- **One version, one changelog entry.** Every release has a section in
  [CHANGELOG.md](CHANGELOG.md), written for users. Mainly `feat` and `fix`
  commits get a line, plus anything breaking, which should say what to do
  about it.

Releasing itself is described in the
[developer guide](docs/DEVELOPMENT.md#releasing).
