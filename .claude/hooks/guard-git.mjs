/**
 * PreToolUse on Bash and PowerShell: the git rules from AGENTS.md, enforced
 * before the command runs rather than remembered.
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
 * `-fd`), and a refspec can carry the force as a `+`.
 *
 * Words are unquoted the way the shell would before any rule looks at them,
 * so `git "commit"`, `g\it add` and `git push origin "main"` are what they
 * run as. A quoted string stays one word, so a message or `echo` that
 * mentions `git commit` is not a `git commit`, and heredoc bodies are
 * skipped. Code that the shell runs from inside a string is checked as a
 * command of its own: `$(...)` and backticks (also inside double quotes and
 * unquoted heredocs), `bash -c`, `eval`, `pwsh -Command` and
 * `-EncodedCommand`, and `Invoke-Expression`. PowerShell input uses its own
 * quoting, where the backtick is the escape character.
 *
 * There is no `if` filter on the hook in settings.json on purpose:
 * `cd svc && git add .` starts with `cd`.
 */
import { currentBranch, deny, readInput } from "./lib.mjs";

const HEREDOC = /<<-?\s*(["']?)([A-Za-z_][A-Za-z0-9_]*)\1\n([\s\S]*?)\n\2\b/g;
const HERE_STRING = /@(["'])\r?\n([\s\S]*?)\r?\n\1@/g;
/** Characters that end a shell segment when they are not quoted. */
const SEPARATORS = new Set([";", "|", "&", "(", ")", "\n"]);
const SHORT_CLUSTER = /^-[A-Za-z]+$/;
const MAIN_REF = /(?:^|[:+])(?:refs\/heads\/)?main$/;
const POSIX_SHELLS = new Set(["sh", "bash", "zsh", "dash", "ksh"]);
const POWERSHELLS = new Set(["pwsh", "powershell"]);
const ENCODED_COMMAND = /^-e(?:c|n[a-z]*)?$/i;
/** Deeper nesting than this is refused rather than unwrapped. */
const MAX_DEPTH = 4;
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

/** `git` for `git`, `/usr/bin/git` or `C:\...\git.exe`, matched loosely. */
const commandName = (word) =>
  word
    .toLowerCase()
    .split(/[\\/]/)
    .pop()
    .replace(/\.(exe|cmd)$/, "");

/**
 * The index just past the `)` that closes the `$(` ending at `start`, or the
 * end of `text`. Quotes inside are skipped so a `)` in a string does not
 * count.
 */
function closingParen(text, start) {
  let depth = 1;
  let quote = null;
  for (let i = start; i < text.length; i += 1) {
    const c = text[i];
    if (quote) {
      if (c === quote) {
        quote = null;
      }
    } else if (c === "'" || c === '"') {
      quote = c;
    } else if (c === "(") {
      depth += 1;
    } else if (c === ")" && --depth === 0) {
      return i + 1;
    }
  }
  return text.length;
}

/**
 * The commands that expanding `text` runs: each `$(...)`, and in POSIX
 * shells each backtick pair. This is what double quotes, unquoted heredocs
 * and PowerShell's `@"..."@` leave live.
 */
function substitutions(text, powershell) {
  const found = [];
  for (let i = 0; i < text.length; i += 1) {
    if (text[i] === (powershell ? "`" : "\\")) {
      i += 1;
    } else if (text.startsWith("$(", i)) {
      const end = closingParen(text, i + 2);
      found.push(text.slice(i + 2, end - 1));
      i = end - 1;
    } else if (!powershell && text[i] === "`") {
      const end = text.indexOf("`", i + 1);
      found.push(text.slice(i + 1, end === -1 ? text.length : end));
      i = end === -1 ? text.length : end;
    }
  }
  return found;
}

/**
 * Split `command` into segments of unquoted words, the way the shell would
 * before running them. Returns the segments and the source of every command
 * the shell would run from inside a string, which the caller checks too.
 */
export function lex(command, shell = "posix") {
  const powershell = shell === "powershell";
  const escape = powershell ? "`" : "\\";
  const nested = [];
  const source = powershell
    ? command.replace(HERE_STRING, (_, quote, body) => {
        if (quote === '"') {
          nested.push(...substitutions(body, true));
        }
        return "''";
      })
    : command.replace(HEREDOC, (_, quote, _tag, body) => {
        if (!quote) {
          nested.push(...substitutions(body, false));
        }
        return "<<HEREDOC";
      });

  const segments = [];
  let words = [];
  let word = null;
  const endWord = () => {
    if (word !== null) {
      words.push(word);
      word = null;
    }
  };
  const endSegment = () => {
    endWord();
    if (words.length) {
      segments.push(words);
    }
    words = [];
  };

  let i = 0;
  while (i < source.length) {
    const c = source[i];
    if (c === escape) {
      // A line continuation joins lines; any other escape is the next char.
      if (source[i + 1] !== "\n") {
        word = (word ?? "") + (source[i + 1] ?? "");
      }
      i += 2;
    } else if (c === "'") {
      const end = source.indexOf("'", i + 1);
      const stop = end === -1 ? source.length : end;
      word = (word ?? "") + source.slice(i + 1, stop);
      i = stop + 1;
    } else if (c === '"') {
      let text = "";
      let j = i + 1;
      while (j < source.length && source[j] !== '"') {
        if (source[j] === escape && j + 1 < source.length) {
          // POSIX keeps a backslash that escapes nothing special.
          const kept = powershell || '$`"\\\n'.includes(source[j + 1]);
          text += kept ? source[j + 1] : source.slice(j, j + 2);
          j += 2;
        } else if (source.startsWith("$(", j)) {
          const end = closingParen(source, j + 2);
          text += source.slice(j, end);
          j = end;
        } else {
          text += source[j];
          j += 1;
        }
      }
      nested.push(...substitutions(text, powershell));
      word = (word ?? "") + text;
      i = j + 1;
    } else if (c === "$" && source[i + 1] === "(") {
      // The substitution's words form their own segment, closed by `)`.
      endSegment();
      i += 2;
    } else if (SEPARATORS.has(c) || (!powershell && c === "`")) {
      endSegment();
      i += 1;
    } else if (/\s/.test(c)) {
      endWord();
      i += 1;
    } else {
      word = (word ?? "") + c;
      i += 1;
    }
  }
  endSegment();
  return { segments, nested };
}

/**
 * Commands that `words` hands to another interpreter as a string, with the
 * shell that will read each one.
 */
function interpreted(words) {
  const found = [];
  words.forEach((word, at) => {
    const name = commandName(word);
    const rest = words.slice(at + 1);
    if (POSIX_SHELLS.has(name)) {
      const flag = rest.findIndex((t) => shortFlag(t, "c"));
      if (flag !== -1 && rest[flag + 1] !== undefined) {
        found.push({ command: rest[flag + 1], shell: "posix" });
      }
    } else if (name === "eval") {
      found.push({ command: rest.join(" "), shell: "posix" });
    } else if (POWERSHELLS.has(name)) {
      rest.forEach((t, i) => {
        if (ENCODED_COMMAND.test(t) && rest[i + 1] !== undefined) {
          const decoded = Buffer.from(rest[i + 1], "base64").toString("utf16le");
          found.push({ command: decoded, shell: "powershell" });
        }
      });
      // Without -File, PowerShell runs the remaining words as a command.
      found.push({ command: rest.join(" "), shell: "powershell" });
    } else if (name === "invoke-expression" || name === "iex") {
      found.push({ command: rest.join(" "), shell: "powershell" });
    }
  });
  return found;
}

/**
 * `{ sub, args }` for the git invocation in one segment's words, or null.
 */
export function parseGit(tokens) {
  const at = tokens.findIndex((t) => commandName(t) === "git");
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
 * The reason `command` must be blocked, or null if it may run. `shell` is
 * "posix" for the Bash tool and "powershell" for the PowerShell tool.
 */
export function check(command, cwd, shell = "posix", depth = 0) {
  if (depth > MAX_DEPTH) {
    return "This command nests shells too deeply for the git guard to check. Run the git part directly.";
  }
  const { segments, nested } = lex(command, shell);
  for (const words of segments) {
    const call = parseGit(words);
    const reason =
      call &&
      (commitRule(call.sub, call.args) ??
        stagingRule(call.sub, call.args) ??
        (call.sub === "push"
          ? pushRule(call.args, cwd)
          : destructiveRule(call.sub, call.args)));
    if (reason) {
      return reason;
    }
    for (const inner of interpreted(words)) {
      const innerReason = check(inner.command, cwd, inner.shell, depth + 1);
      if (innerReason) {
        return innerReason;
      }
    }
  }
  for (const inner of nested) {
    const innerReason = check(inner, cwd, shell, depth + 1);
    if (innerReason) {
      return innerReason;
    }
  }
  return null;
}

// Run as a hook only when executed directly, so tests can import `check`.
if (process.argv[1]?.endsWith("guard-git.mjs")) {
  const input = readInput();
  const shell = input.tool_name === "PowerShell" ? "powershell" : "posix";
  const reason = check(
    input.tool_input?.command ?? "",
    input.cwd ?? process.cwd(),
    shell
  );
  if (reason) {
    deny(reason);
  }
}
