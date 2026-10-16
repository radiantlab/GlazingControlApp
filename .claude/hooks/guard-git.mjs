/**
 * PreToolUse on Bash: the git rules from AGENTS.md, enforced before the
 * command runs rather than remembered.
 *
 * Adapted from adulbrich/eecs-capstone (.claude/hooks/guard-git.mjs),
 * MIT License, Copyright (c) 2026 Alex Ulbrich. That repository lets agents
 * commit; this one does not, so the rules are stricter and the commit-message
 * check is gone.
 *
 * - No commits: `commit`, `commit-tree`, `cherry-pick`, `revert`, `am`,
 *   `rebase`, and `merge` or `pull` unless `--ff-only` (a fast-forward moves
 *   a branch without creating a commit).
 * - No staging: `add`, `rm`, `mv`, `update-index`, and `apply --index` or
 *   `--cached`. Unstaging (`restore --staged`, `reset` without `--hard`) is
 *   allowed, because it hands control back to the human.
 * - No push to main, and no force push at all.
 * - No `reset --hard`, `clean -f`, `branch -D`, or a working-tree wipe
 *   through `checkout .` and `restore .`.
 *
 * Everything else, including status, diff, log, fetch, switch, stash and a
 * plain push of a feature branch, goes through. Exit 2 blocks; stderr is the
 * reason the model reads.
 *
 * The command line is tokenized rather than matched as text: git's global
 * options (`git -C dir add`, `git -c k=v commit`) sit between `git` and the
 * subcommand, flags come in short, long and clustered forms (`-f`, `--force`,
 * `-fd`), and a refspec can carry the force as a `+`. Quoted strings and
 * heredoc bodies are blanked before parsing, so a message or `echo` that
 * mentions `git commit` is not a `git commit`. There is no `if` filter on the
 * hook in settings.json on purpose: `cd svc && git add .` starts with `cd`.
 */
import { currentBranch, deny, readInput } from "./lib.mjs";

const HEREDOC = /<<-?\s*(["']?)([A-Za-z_][A-Za-z0-9_]*)\1\n([\s\S]*?)\n\2\b/g;
const QUOTED = /"(?:[^"\\]|\\.)*"|'[^']*'/g;
const SEGMENT = /\s*(?:&&|\|\||;|\||&)\s*|\n|\$\(|`|\(|\)/;
const SHORT_CLUSTER = /^-[A-Za-z]+$/;
const WHITESPACE = /\s+/;
const MAIN_REF = /(?:^|[:+])(?:refs\/heads\/)?main$/;
/** Global options that take a separate argument. */
const GLOBAL_WITH_ARG = new Set([
  "-C",
  "-c",
  "--git-dir",
  "--work-tree",
  "--exec-path",
  "--namespace",
]);

const NO_COMMITS =
  "AGENTS.md: agents never create Git commits. Leave the change in the working tree and tell the user it is ready to review and commit.";
const NO_STAGING =
  "AGENTS.md: agents never stage changes. Leave the change unstaged and tell the user which paths are ready to review.";

const isDot = (t) => t === "." || t === "./" || t === ":/";
/** A short flag cluster carrying `letter`, as `-f` or `-fd` carry `f`. */
const shortFlag = (t, letter) =>
  SHORT_CLUSTER.test(t) && t.slice(1).includes(letter);
/** `--long` or the short `letter` in any cluster, as `--force` or `-fd`. */
const hasFlag = (args, long, letter) =>
  args.some((t) => t === long || (letter && shortFlag(t, letter)));

/**
 * `{ sub, args }` for the git invocation in one shell segment, or null.
 */
export function parseGit(segment) {
  const tokens = segment.trim().split(WHITESPACE);
  const at = tokens.findIndex(
    (t) => t === "git" || t.endsWith("/git") || t.toLowerCase().endsWith("git.exe")
  );
  if (at === -1) {
    return null;
  }
  let i = at + 1;
  while (i < tokens.length && tokens[i].startsWith("-")) {
    i += GLOBAL_WITH_ARG.has(tokens[i]) ? 2 : 1;
  }
  return { sub: tokens[i] ?? "", args: tokens.slice(i + 1) };
}

function commitRule(sub, args) {
  switch (sub) {
    case "commit":
    case "commit-tree":
    case "cherry-pick":
    case "am":
    case "rebase":
      return NO_COMMITS;
    case "revert":
      return hasFlag(args, "--no-commit", "n") ? null : NO_COMMITS;
    case "merge":
    case "pull":
      return args.includes("--ff-only")
        ? null
        : `${NO_COMMITS} For updating a branch, \`git ${sub} --ff-only\` is allowed.`;
    default:
      return null;
  }
}

function stagingRule(sub, args) {
  switch (sub) {
    case "add":
    case "rm":
    case "mv":
    case "update-index":
      return NO_STAGING;
    case "apply":
      return hasFlag(args, "--index") || hasFlag(args, "--cached")
        ? NO_STAGING
        : null;
    default:
      return null;
  }
}

function pushRule(args, cwd) {
  const forced =
    hasFlag(args, "--force", "f") ||
    args.some(
      (t) =>
        t.startsWith("--force-with-lease") ||
        t === "--force-if-includes" ||
        (t.startsWith("+") && t.length > 1)
    );
  if (forced) {
    return "No force push from an agent. Ask the user to run it if it is really needed.";
  }
  const named = args.filter((t) => !t.startsWith("-"));
  // `git push` or `git push origin` pushes the current branch.
  const refs = named.slice(1);
  const onMain = () => currentBranch(cwd) === "main";
  const atMain =
    refs.some((t) => MAIN_REF.test(t)) ||
    ((refs.length === 0 || refs.some((t) => t === "HEAD")) && onMain());
  return atMain
    ? "AGENTS.md: never push to main. Changes reach main only through a squash-merged pull request."
    : null;
}

function destructiveRule(sub, args) {
  switch (sub) {
    case "reset":
      return args.includes("--hard")
        ? "No `git reset --hard` from an agent: it discards uncommitted work the user may want. Ask them to run it."
        : null;
    case "clean":
      return hasFlag(args, "--force", "f")
        ? "No `git clean -f` from an agent. Ask the user to run it."
        : null;
    case "branch": {
      const forceDelete =
        args.some((t) => shortFlag(t, "D")) ||
        (hasFlag(args, "--delete", "d") && hasFlag(args, "--force", "f"));
      return forceDelete
        ? "No `git branch -D` from an agent. Use `-d`, or ask the user to force-delete."
        : null;
    }
    case "checkout":
      return args.some(isDot)
        ? "No working-tree wipe (`git checkout .`) from an agent. Name the paths to restore."
        : null;
    case "restore": {
      const indexOnly =
        hasFlag(args, "--staged", "S") && !hasFlag(args, "--worktree", "W");
      return args.some(isDot) && !indexOnly
        ? "No working-tree wipe (`git restore .`) from an agent. Name the paths to restore."
        : null;
    }
    default:
      return null;
  }
}

/**
 * The reason `command` must be blocked, or null if it may run.
 */
export function check(command, cwd) {
  if (!/\bgit\b/i.test(command)) {
    return null;
  }
  const detectable = command
    .replace(HEREDOC, "<<HEREDOC")
    .replace(QUOTED, '""');
  for (const segment of detectable.split(SEGMENT)) {
    const call = parseGit(segment);
    if (!call) {
      continue;
    }
    const reason =
      commitRule(call.sub, call.args) ??
      stagingRule(call.sub, call.args) ??
      (call.sub === "push"
        ? pushRule(call.args, cwd)
        : destructiveRule(call.sub, call.args));
    if (reason) {
      return reason;
    }
  }
  return null;
}

// Run as a hook only when executed directly, so tests can import `check`.
if (process.argv[1]?.endsWith("guard-git.mjs")) {
  const input = readInput();
  const reason = check(input.tool_input?.command ?? "", input.cwd ?? process.cwd());
  if (reason) {
    deny(reason);
  }
}
