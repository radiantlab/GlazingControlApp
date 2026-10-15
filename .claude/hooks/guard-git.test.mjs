// Tests for guard-git.mjs. Run from the repository root:
//   node --test .claude/hooks/guard-git.test.mjs
import assert from "node:assert/strict";
import { execFileSync, spawnSync } from "node:child_process";
import { mkdtempSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { after, describe, it } from "node:test";
import { fileURLToPath } from "node:url";

import { check } from "./guard-git.mjs";

const HOOK = fileURLToPath(new URL("./guard-git.mjs", import.meta.url));

/** A throwaway repository on `branch`, so push rules see a real branch. */
function repoOn(branch) {
  const dir = mkdtempSync(join(tmpdir(), "guard-git-"));
  const env = Object.fromEntries(
    Object.entries(process.env).filter(([key]) => !key.startsWith("GIT_"))
  );
  execFileSync("git", ["init", "-q", "-b", branch, dir], { env });
  return dir;
}

const onMain = repoOn("main");
const onFeature = repoOn("docs/example");
after(() => {
  rmSync(onMain, { recursive: true, force: true });
  rmSync(onFeature, { recursive: true, force: true });
});

const blocked = (command, cwd = onFeature) =>
  assert.notEqual(check(command, cwd), null, `expected block: ${command}`);
const allowed = (command, cwd = onFeature) =>
  assert.equal(check(command, cwd), null, `expected allow: ${command}`);

describe("commits", () => {
  it("blocks every way of creating a commit", () => {
    for (const command of [
      "git commit -m 'docs: x'",
      "git commit --amend --no-edit",
      "git -C svc commit -m x",
      "git -c user.name=x commit -m y",
      "cd svc && git commit -m x",
      "git commit-tree HEAD^{tree}",
      "git cherry-pick abc123",
      "git revert abc123",
      "git rebase main",
      "git am < patch.mbox",
      "git merge feature",
      "git pull",
      "git pull origin main",
      "/usr/bin/git commit -m x",
      "echo ok; git commit -m x",
      "true $(git commit -m x)",
    ]) {
      blocked(command);
    }
  });

  it("allows fast-forward updates and no-commit reverts", () => {
    allowed("git pull --ff-only");
    allowed("git merge --ff-only origin/main");
    allowed("git revert --no-commit abc123");
  });

  it("ignores git commands inside quoted text and heredocs", () => {
    allowed("echo 'never run git commit here'");
    allowed('grep -n "git add ." CONTRIBUTING.md');
    allowed("cat <<'EOF'\ngit commit -m x\nEOF");
  });
});

describe("staging", () => {
  it("blocks staging", () => {
    for (const command of [
      "git add CONTRIBUTING.md",
      "git add -A",
      "git rm old.md",
      "git mv a.md b.md",
      "git apply --index fix.patch",
      "git apply --cached fix.patch",
      "git update-index --add x",
    ]) {
      blocked(command);
    }
  });

  it("allows unstaging and patch checks", () => {
    allowed("git restore --staged CONTRIBUTING.md");
    allowed("git reset CONTRIBUTING.md");
    allowed("git apply --check fix.patch");
  });
});

describe("push", () => {
  it("blocks pushes to main", () => {
    blocked("git push origin main");
    blocked("git push origin HEAD:main");
    blocked("git push origin HEAD:refs/heads/main");
    blocked("git push", onMain);
    blocked("git push origin HEAD", onMain);
  });

  it("blocks force pushes anywhere", () => {
    blocked("git push --force");
    blocked("git push -f origin docs/example");
    blocked("git push --force-with-lease");
    blocked("git push origin +docs/example");
  });

  it("allows a plain push of a feature branch", () => {
    allowed("git push");
    allowed("git push -u origin docs/example");
  });
});

describe("destructive commands", () => {
  it("blocks them", () => {
    for (const command of [
      "git reset --hard",
      "git clean -fd",
      "git branch -D old",
      "git branch --delete --force old",
      "git checkout .",
      "git restore .",
    ]) {
      blocked(command);
    }
  });

  it("allows the everyday read and branch commands", () => {
    for (const command of [
      "git status --short",
      "git diff main...HEAD",
      "git log --oneline -5",
      "git fetch origin",
      "git switch -c docs/new main",
      "git checkout -b fix/x",
      "git stash",
      "git branch -d merged",
      "git restore CONTRIBUTING.md",
      "ls -la",
    ]) {
      allowed(command);
    }
  });
});

describe("as a hook process", () => {
  const run = (command) =>
    spawnSync(process.execPath, [HOOK], {
      input: JSON.stringify({ tool_input: { command }, cwd: onFeature }),
      encoding: "utf8",
    });

  it("exits 2 with the reason on stderr when blocking", () => {
    const result = run("git commit -m x");
    assert.equal(result.status, 2);
    assert.match(result.stderr, /never create Git commits/);
  });

  it("exits 0 when allowing", () => {
    assert.equal(run("git status").status, 0);
  });
});
