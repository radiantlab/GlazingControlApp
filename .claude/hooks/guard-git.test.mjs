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
    allowed("echo '$(git commit -m x)'");
    allowed("cat <<'EOF'\n$(git commit -m x)\nEOF");
    allowed('gh pr create --title "x" --body "Run git commit yourself"');
    allowed('git log --grep "git commit" --oneline');
  });
});

describe("quoting", () => {
  it("unquotes words before applying the rules", () => {
    for (const command of [
      'git "commit" -m x',
      "git 'add' .",
      '"git" commit -m x',
      'g"it" add .',
      'git com"mit" -m x',
      "g\\it commit -m x",
      'git -C "my dir" commit -m x',
      '"/usr/bin/git" add .',
      'git push "--force"',
      'git reset "--hard"',
      'git push origin "main"',
    ]) {
      blocked(command);
    }
  });

  it("checks commands the shell runs from inside a string", () => {
    for (const command of [
      'echo "$(git commit -m x)"',
      'echo "`git add .`"',
      "cat <<EOF\n$(git commit -m x)\nEOF",
      'bash -c "git commit -m x"',
      "sh -c 'git add .'",
      "bash -lc 'cd svc && git add .'",
      'eval "git commit -m x"',
      "xargs sh -c 'git add \"$1\"' _",
    ]) {
      blocked(command);
    }
  });

  it("still allows quoted arguments to allowed commands", () => {
    allowed('git push -u origin "docs/example"');
    allowed('git switch -c "fix/x"');
    allowed('git log --format="%h %s" -5');
    allowed('bash -c "git status --short"');
  });
});

describe("PowerShell", () => {
  const ps = "powershell";
  const blockedPs = (command) =>
    assert.notEqual(check(command, onFeature, ps), null, `expected block: ${command}`);
  const allowedPs = (command) =>
    assert.equal(check(command, onFeature, ps), null, `expected allow: ${command}`);
  const encoded = (command) => Buffer.from(command, "utf16le").toString("base64");

  it("blocks the same commands with PowerShell quoting", () => {
    for (const command of [
      "git commit -m 'docs: x'",
      "& git add .",
      '& "C:\\Program Files\\Git\\cmd\\git.exe" commit -m x',
      "GIT commit -m x",
      "g`it commit -m x",
      "git push origin main; Write-Host done",
      'Write-Output "$(git commit -m x)"',
      "Write-Output $(git add .)",
      "@\"\n$(git commit -m x)\n\"@",
      'pwsh -NoProfile -Command "git add ."',
      "powershell.exe git commit -m x",
      `pwsh -EncodedCommand ${encoded("git commit -m x")}`,
      'Invoke-Expression "git commit -m x"',
      "iex 'git add .'",
      "Invoke-Command -ScriptBlock { git commit -m x }",
    ]) {
      blockedPs(command);
    }
  });

  it("treats the backtick as an escape, not a substitution", () => {
    allowedPs('Write-Host "run `"git add`" yourself"');
    allowedPs("Write-Host 'git commit'");
    allowedPs("@'\n$(git commit -m x)\n'@");
    allowedPs('Select-String -Pattern "git add ." -Path CONTRIBUTING.md');
    allowedPs("git status --short");
    allowedPs('git push -u origin "docs/example"');
  });
});

describe("nesting", () => {
  it("refuses commands nested deeper than it unwraps", () => {
    const deep = "bash -c " + JSON.stringify(
      "bash -c " + JSON.stringify(
        "bash -c " + JSON.stringify(
          "bash -c " + JSON.stringify("bash -c " + JSON.stringify("ls"))
        )
      )
    );
    blocked(deep);
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
  const run = (command, toolName = "Bash") =>
    spawnSync(process.execPath, [HOOK], {
      input: JSON.stringify({
        tool_name: toolName,
        tool_input: { command },
        cwd: onFeature,
      }),
      encoding: "utf8",
    });

  it("reads PowerShell tool input with PowerShell quoting", () => {
    assert.equal(run("g`it commit -m x", "PowerShell").status, 2);
    assert.equal(run("git status", "PowerShell").status, 0);
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
