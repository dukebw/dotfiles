#!/usr/bin/env python3
"""GitHub state, schedule gate and bookkeeping for the pr-sweep skill."""

import argparse
import concurrent.futures
import datetime as dt
import json
import re
import subprocess
import time
from pathlib import Path

REPO = "basetenlabs/baseten"
MAIN_CHECKOUT = Path.home() / "work/baseten"
LEDGER = Path.home() / ".local/state/pr-sweep/ledger.jsonl"
GATE_STATE = LEDGER.with_name("gate.json")
STUCK_AFTER_CHECKS = 3
STALE_DAYS = 30
MAX_FIX_PUSHES_7D = 2
MAX_B200_TICKS_PER_HEAD = 2
B200_BOT = "baseten-mpci-checkpr-app[bot]"
B200_MARKER = "<!-- mp-gpu-controls -->"
B200_UNTICKED = re.compile(r"^- \[ \] Run B200", re.M)
SWEEP_WORKTREE = "baseten-sweep-pr{number}"
SWEEP_BRANCH = "bduke/sweep-pr{number}"
NOTIFIER = "/opt/homebrew/bin/terminal-notifier"
FAILED = {"FAILURE", "TIMED_OUT", "STARTUP_FAILURE", "ERROR"}

DETAIL_QUERY = """
query($owner:String!,$name:String!,$number:Int!){ repository(owner:$owner,name:$name){
  defaultBranchRef{name}
  pullRequest(number:$number){
    number state title url isDraft createdAt
    baseRefName headRefName headRefOid
    reviewDecision mergeable
    autoMergeRequest{enabledAt}
    labels(first:30){nodes{name}}
    reviewThreads(first:100){nodes{isResolved comments(first:1){nodes{author{__typename}}}}}
    commits(last:1){nodes{commit{statusCheckRollup{contexts(first:100){nodes{__typename
      ... on CheckRun{name status conclusion databaseId isRequired(pullRequestNumber:$number)}
      ... on StatusContext{context state description isRequired(pullRequestNumber:$number)}
    }}}}}}
    timelineItems(last:40, itemTypes:[ISSUE_COMMENT, PULL_REQUEST_REVIEW, HEAD_REF_FORCE_PUSHED_EVENT,
        PULL_REQUEST_COMMIT, READY_FOR_REVIEW_EVENT, CONVERT_TO_DRAFT_EVENT, REOPENED_EVENT]){nodes{__typename
      ... on IssueComment{createdAt author{__typename}}
      ... on PullRequestReview{submittedAt author{__typename}}
      ... on HeadRefForcePushedEvent{createdAt afterCommit{oid}}
      ... on PullRequestCommit{commit{oid committedDate}}
      ... on ReadyForReviewEvent{createdAt}
      ... on ConvertToDraftEvent{createdAt}
      ... on ReopenedEvent{createdAt}
    }}
  }
}}
"""


def run(*cmd, cwd=None):
    proc = subprocess.run(cmd, cwd=cwd, text=True, capture_output=True)
    if proc.returncode:
        shown = " ".join(str(part) for part in cmd[:5])
        raise SystemExit(f"{shown} failed: {proc.stderr.strip() or proc.stdout.strip()}")
    return proc.stdout.strip()


def git(*args, cwd=MAIN_CHECKOUT):
    return run("git", *args, cwd=cwd)


def now():
    return dt.datetime.now(dt.timezone.utc)


def read_ledger():
    if not LEDGER.exists():
        return []
    return [json.loads(line) for line in LEDGER.read_text().splitlines() if line.strip()]


def append_ledger(**entry):
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a") as ledger:
        ledger.write(json.dumps({"ts": now().isoformat(timespec="seconds"), **entry}) + "\n")


def notify(number, event, message, pr_title=None):
    """Desktop notification that opens the PR when clicked."""
    subtitle = ["-subtitle", pr_title] if pr_title else []
    run(NOTIFIER, "-group", f"pr-sweep-{number}-{event}", "-title", f"PR sweep: #{number} {event}", *subtitle,
        "-message", message, "-sound", "Glass", "-open", f"https://github.com/{REPO}/pull/{number}")


def fetch_pr(repo, number):
    owner, name = repo.split("/")
    # GitHub computes mergeability lazily; the first read after a push is often UNKNOWN.
    for _ in range(4):
        data = json.loads(
            run("gh", "api", "graphql", "-f", f"query={DETAIL_QUERY}",
                "-f", f"owner={owner}", "-f", f"name={name}", "-F", f"number={number}")
        )["data"]["repository"]
        pr = data["pullRequest"]
        if pr["mergeable"] != "UNKNOWN":
            break
        time.sleep(3)
    return {**pr, "repo": repo, "defaultBranch": data["defaultBranchRef"]["name"]}


def fetch_open_prs():
    found = json.loads(
        run("gh", "search", "prs", "--author", "@me", "--state", "open", "--limit", "100",
            "--json", "repository,number")
    )
    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        prs = pool.map(lambda hit: fetch_pr(hit["repository"]["nameWithOwner"], hit["number"]), found)
        return [pr for pr in prs if pr["state"] == "OPEN"]


def latest_checks(pr):
    rollup = pr["commits"]["nodes"][0]["commit"]["statusCheckRollup"] or {"contexts": {"nodes": []}}
    checks = {}
    for context in rollup["contexts"]["nodes"]:
        if context["__typename"] == "StatusContext":
            done = context["state"] not in ("PENDING", "EXPECTED")
            checks[context["context"]] = {
                "name": context["context"], "done": done, "conclusion": context["state"],
                "description": context["description"] or "", "required": context["isRequired"],
            }
            continue
        # Re-runs leave older check runs of the same name in the rollup; the newest is the verdict.
        previous = checks.get(context["name"])
        if previous is None or (context["databaseId"] or 0) > previous["id"]:
            checks[context["name"]] = {
                "name": context["name"], "done": context["status"] == "COMPLETED",
                "conclusion": context["conclusion"], "description": "",
                "required": context["isRequired"], "id": context["databaseId"] or 0,
            }
    return checks


def idle_days(pr, sweep_shas):
    """Days since a person last touched the PR; bots and this sweep's own pushes don't count."""
    seen = [pr["createdAt"]]
    for item in pr["timelineItems"]["nodes"]:
        kind = item["__typename"]
        if kind in ("IssueComment", "PullRequestReview"):
            if (item["author"] or {}).get("__typename") != "Bot":
                seen.append(item.get("createdAt") or item.get("submittedAt"))
        elif kind == "HeadRefForcePushedEvent":
            if (item["afterCommit"] or {}).get("oid") not in sweep_shas:
                seen.append(item["createdAt"])
        elif kind == "PullRequestCommit":
            if item["commit"]["oid"] not in sweep_shas:
                seen.append(item["commit"]["committedDate"])
        else:
            seen.append(item["createdAt"])
    latest = max(dt.datetime.fromisoformat(stamp.replace("Z", "+00:00")) for stamp in seen if stamp)
    return (now() - latest).days


def summarize(pr, prs, ledger):
    head = pr["headRefOid"]
    managed = pr["repo"] == REPO
    mine = [entry for entry in ledger if entry["pr"] == pr["number"]] if managed else []
    siblings = [other for other in prs if other["repo"] == pr["repo"]]
    parent = next((o["number"] for o in siblings if o["headRefName"] == pr["baseRefName"]), None)
    children = [o["number"] for o in siblings if o["baseRefName"] == pr["headRefName"]]
    labels = {label["name"] for label in pr["labels"]["nodes"]}

    checks = latest_checks(pr)
    mp_status = checks.get("mp-status", {"conclusion": None, "description": ""})
    base_stale = mp_status["conclusion"] == "FAILURE" and bool(re.search(r"\brebase\b", mp_status["description"], re.I))
    needs_tick = mp_status["conclusion"] == "PENDING" and "tick Run B200" in mp_status["description"]
    gating = [c for c in checks.values() if c["required"] and c["name"] != "Approval checks"]
    red = [c["name"] for c in gating if c["conclusion"] in FAILED and not (c["name"] == "mp-status" and base_stale)]
    running = [c for c in gating if not c["done"] and not (c["name"] == "mp-status" and needs_tick)]
    ci = "red" if red else "stale-base" if base_stale else "pending" if running else "needs-b200" if needs_tick else "green"

    human_threads = sum(
        1 for thread in pr["reviewThreads"]["nodes"]
        if not thread["isResolved"]
        and ((thread["comments"]["nodes"] or [{}])[0].get("author") or {}).get("__typename") != "Bot"
    )
    idle = idle_days(pr, {sha for entry in ledger for sha in entry.get("shas", [])})
    approved = pr["reviewDecision"] == "APPROVED"
    conflicting = pr["mergeable"] == "CONFLICTING"
    automerge = pr["autoMergeRequest"] is not None
    week_ago = (now() - dt.timedelta(days=7)).isoformat()
    fix_pushes = sum(1 for e in mine if e["action"] == "fix" and e["ts"] >= week_ago)
    ticks = sum(1 for e in mine if e["action"] == "tick" and e["sha"] == head)
    reruns = sum(1 for e in mine if e["action"] == "rerun" and e["sha"] == head)

    actions = []
    if managed and idle >= STALE_DAYS and not approved and not children and "keep-open" not in labels:
        actions = ["close"]
    elif managed and not pr["isDraft"]:
        if conflicting or base_stale:
            actions.append("rebase")
        else:
            if red:
                actions.append("fix-ci")
            if needs_tick and not ticks:
                actions.append("tick-b200")
        if (approved and not automerge and not conflicting and not human_threads
                and pr["baseRefName"] == pr["defaultBranch"] and "do not merge" not in labels):
            actions.append("enable-automerge")

    blocked = {e["blocks"]: e["note"] for e in mine if e["action"] == "needs-you" and e["sha"] == head}
    if fix_pushes >= MAX_FIX_PUSHES_7D:
        blocked.setdefault("fix-ci", f"{fix_pushes} fix pushes in the last 7 days did not turn CI green")
    blocked = {action: note for action, note in blocked.items() if action in actions}
    actions = [action for action in actions if action not in blocked]

    waiting = []
    if not managed:
        waiting.append(f"not managed: only {REPO} is swept")
    if pr["isDraft"]:
        waiting.append("draft")
    if pr["reviewDecision"] == "REVIEW_REQUIRED":
        waiting.append("review")
    if pr["reviewDecision"] == "CHANGES_REQUESTED":
        waiting.append("changes requested")
    approval = checks.get("Approval checks")
    if approval and approval["conclusion"] != "SUCCESS" and approval["description"]:
        waiting.append(approval["description"])
    if human_threads:
        waiting.append(f"{human_threads} unresolved review threads from people")
    if "do not merge" in labels:
        waiting.append("do not merge label")
    if parent:
        waiting.append(f"stacked on #{parent}")
    if ci == "pending":
        waiting.append("CI running")
    if automerge:
        waiting.append("auto-merge is on")

    summary = {
        "pr": pr["number"], "repo": pr["repo"], "title": pr["title"], "url": pr["url"],
        "head": head[:10], "base": pr["baseRefName"], "parent": parent, "children": children,
        "review": pr["reviewDecision"], "mergeable": pr["mergeable"], "ci": ci,
        "failing": sorted(c["name"] for c in checks.values() if c["conclusion"] in FAILED and c["name"] != "Approval checks"),
        "idle_days": idle, "fix_pushes_7d": fix_pushes, "b200_ticks_for_head": ticks, "reruns_for_head": reruns,
        "actions": actions, "blocked": blocked, "waiting": waiting,
    }
    return {key: value for key, value in summary.items() if value not in (None, [], {}, 0)} | {"actions": actions}


def snapshot():
    prs = fetch_open_prs()
    ledger = read_ledger()
    summaries = sorted((summarize(pr, prs, ledger) for pr in prs), key=lambda s: (s["repo"] != REPO, s["repo"], s["pr"]))
    by_number = {(s["repo"], s["pr"]): s for s in summaries}
    # A rebase of a lower PR pushes the whole stack and restarts its CI, so CI work above it waits.
    for summary in summaries:
        ancestor = summary.get("parent")
        while ancestor:
            below = by_number[(summary["repo"], ancestor)]
            if "rebase" in below["actions"]:
                summary["actions"] = [a for a in summary["actions"] if a not in ("fix-ci", "tick-b200")]
                summary.setdefault("waiting", []).append(f"rebase of #{ancestor}")
                break
            ancestor = below.get("parent")
    return summaries


def my_open_prs():
    return json.loads(
        run("gh", "pr", "list", "--repo", REPO, "--author", "@me", "--state", "open", "--limit", "100",
            "--json", "number,title,headRefName,headRefOid,baseRefName")
    )


def stack_of(number):
    """The PRs stacked with `number`, bottom first."""
    prs = my_open_prs()
    by_head = {pr["headRefName"]: pr for pr in prs}
    stack = [pr for pr in prs if pr["number"] == number]
    if not stack:
        raise SystemExit(f"#{number} is not one of my open PRs in {REPO}")
    while stack[0]["baseRefName"] in by_head:
        stack.insert(0, by_head[stack[0]["baseRefName"]])
    while True:
        children = [pr for pr in prs if pr["baseRefName"] == stack[-1]["headRefName"]]
        if not children:
            return stack
        if len(children) > 1:
            raise SystemExit(f"#{stack[-1]['number']} has several child PRs; a stack that branches is not supported")
        stack.append(children[0])


def list_worktrees():
    worktrees, current = [], {}
    for line in [*git("worktree", "list", "--porcelain").splitlines(), ""]:
        if line:
            key, _, value = line.partition(" ")
            current[key] = value
        elif current:
            worktrees.append(current)
            current = {}
    return worktrees


def is_clean(path):
    if git("status", "--porcelain", "--untracked-files=no", cwd=path):
        return False
    return not any((Path(path) / git("rev-parse", "--git-path", name, cwd=path)).exists()
                   for name in ("rebase-merge", "rebase-apply", "MERGE_HEAD"))


def cmd_snapshot(_):
    for summary in snapshot():
        print(json.dumps(summary))


def gate_lines(state):
    managed = [s for s in snapshot() if s["repo"] == REPO]
    for number, title in state.get("open", {}).items():
        if int(number) not in {s["pr"] for s in managed}:
            if run("gh", "pr", "view", number, "--repo", REPO, "--json", "state", "--jq", ".state") == "MERGED":
                notify(number, "merged", "Merged into master.", title)
    due = {}
    for summary in managed:
        if summary["actions"]:
            line = f"#{summary['pr']} {summary['head']} {' '.join(summary['actions'])}"
            due[line] = state.get("due", {}).get(line, 0) + 1
            if due[line] == STUCK_AFTER_CHECKS:
                notify(summary["pr"], "sweep is stuck",
                       f"{' '.join(summary['actions'])} has been due for {STUCK_AFTER_CHECKS} checks in a row. "
                       "See the [run] pr-sweep session.", summary["title"])
    state.update(open={str(s["pr"]): s["title"] for s in managed}, due=due)
    return list(due)


def cmd_gate(_):
    """Schedule check: one `#<pr> <head> <actions>` line per PR with work due, nothing otherwise."""
    state = json.loads(GATE_STATE.read_text()) if GATE_STATE.exists() else {}
    today = dt.date.today().isoformat()
    try:
        print(*gate_lines(state), sep="\n")
    # The scheduler pauses a schedule whose check exits non-zero, so a failure skips this slot instead.
    except (Exception, SystemExit) as error:
        if state.get("error_day") != today:
            state["error_day"] = today
            run(NOTIFIER, "-group", "pr-sweep-gate", "-title", "PR sweep: check is failing",
                "-message", str(error)[:300], "-sound", "Glass")
    GATE_STATE.parent.mkdir(parents=True, exist_ok=True)
    GATE_STATE.write_text(json.dumps(state))


def cmd_worktree(args):
    stack = stack_of(args.pr)
    top = stack[-1]
    git("fetch", "--quiet", "origin", "master", top["headRefName"])
    # Never the main checkout (first entry): its stack holds commits that are not these PRs.
    in_sync = [w for w in list_worktrees()[1:]
               if w["HEAD"] == top["headRefOid"] and "branch" in w and is_clean(w["worktree"])]
    if in_sync:
        path = Path(in_sync[0]["worktree"])
    else:
        path = MAIN_CHECKOUT.parent / SWEEP_WORKTREE.format(number=top["number"])
        branch = SWEEP_BRANCH.format(number=top["number"])
        if not path.exists():
            git("worktree", "add", "--quiet", "-B", branch, str(path), top["headRefOid"])
        elif is_clean(path):
            git("checkout", "--quiet", "-B", branch, top["headRefOid"], cwd=path)
        else:
            raise SystemExit(f"{path} has uncommitted changes or an unfinished rebase")
    commits = git("rev-list", "--reverse", "origin/master..HEAD", cwd=path).split()
    heads = [pr["headRefOid"] for pr in stack]
    if commits[-len(heads):] != heads:
        raise SystemExit(f"{path}: the top {len(heads)} commits are not the heads of {[pr['number'] for pr in stack]}")
    print(json.dumps({"path": str(path), "stack": [pr["number"] for pr in stack],
                      "commits_below_stack": len(commits) - len(heads)}))


def cmd_log(args):
    stack = stack_of(args.pr)
    head, title = next((pr["headRefOid"], pr["title"]) for pr in stack if pr["number"] == args.pr)
    entry = {"pr": args.pr, "action": args.action, "sha": head, "shas": [pr["headRefOid"] for pr in stack]}
    if args.action == "needs-you":
        if not args.blocks or not args.note:
            raise SystemExit("needs-you requires --blocks <action> and --note <why>")
        entry["blocks"] = args.blocks
        if any(all(old.get(key) == entry[key] for key in ("pr", "action", "sha", "blocks")) for old in read_ledger()):
            print(f"#{args.pr}: {args.blocks} is already recorded as needs-you for {head[:10]}")
            return
    if args.note:
        entry["note"] = args.note
    append_ledger(**entry)
    event, message = {
        "needs-you": ("needs you", f"{args.blocks}: {args.note}"),
        "rebase": ("rebased", "Rebased onto master and pushed; CI is restarting."),
        "fix": ("CI fix pushed", "Pushed a fix for the failing check; CI is restarting."),
        "rerun": ("CI re-run", "Re-ran the failed jobs."),
    }[args.action]
    notify(args.pr, event, args.note or message, title)


def cmd_tick(args):
    head = run("gh", "api", f"repos/{REPO}/pulls/{args.pr}", "--jq", ".head.sha")
    ticks = sum(1 for e in read_ledger() if e["pr"] == args.pr and e["action"] == "tick" and e["sha"] == head)
    if ticks >= MAX_B200_TICKS_PER_HEAD:
        raise SystemExit(f"#{args.pr}: already ticked Run B200 {ticks} times on {head[:10]}")
    controls = run(
        "gh", "api", "--paginate", f"repos/{REPO}/issues/{args.pr}/comments?per_page=100", "--jq",
        f'.[] | select(.user.login == "{B200_BOT}" and (.body | startswith("{B200_MARKER}"))) | {{id, body}}',
    ).splitlines()
    comment = json.loads(controls[-1]) if controls else {"body": ""}
    if f"<!-- sha:{head} -->" not in comment["body"] or not B200_UNTICKED.search(comment["body"]):
        raise SystemExit(f"#{args.pr}: no unticked Run B200 box for {head[:10]}")
    run("gh", "api", "-X", "PATCH", f"repos/{REPO}/issues/comments/{comment['id']}",
        "-f", f"body={B200_UNTICKED.sub('- [x] Run B200', comment['body'], count=1)}")
    append_ledger(pr=args.pr, action="tick", sha=head)
    notify(args.pr, "B200 suite started", f"Ticked Run B200 on {head[:10]}.")
    print(f"#{args.pr}: ticked Run B200 on {head[:10]}")


def cmd_automerge(args):
    run("gh", "pr", "merge", str(args.pr), "--repo", REPO, "--auto", "--squash")
    append_ledger(pr=args.pr, action="automerge")
    notify(args.pr, "auto-merge enabled", "It merges once the required checks pass.")
    print(f"#{args.pr}: auto-merge (squash) enabled")


def cmd_close(args):
    run("gh", "pr", "close", str(args.pr), "--repo", REPO)
    append_ledger(pr=args.pr, action="close", note=args.note)
    notify(args.pr, "closed", f"Closed as {args.note}; the branch is kept, so reopening restores it.")
    print(f"#{args.pr}: closed")


def cmd_gc(_):
    open_numbers = {pr["number"] for pr in my_open_prs()}
    pattern = re.compile(SWEEP_WORKTREE.format(number=r"(\d+)"))
    for worktree in list_worktrees()[1:]:
        match = pattern.fullmatch(Path(worktree["worktree"]).name)
        if match and int(match[1]) not in open_numbers:
            git("worktree", "remove", worktree["worktree"])
            git("branch", "-D", SWEEP_BRANCH.format(number=match[1]))
            print(f"removed {worktree['worktree']}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("snapshot", help="one JSON line per open PR, with the actions due").set_defaults(run=cmd_snapshot)
    commands.add_parser("gate", help="print the actions due; exit 1 when there are none").set_defaults(run=cmd_gate)
    commands.add_parser("gc", help="remove sweep worktrees whose PR is no longer open").set_defaults(run=cmd_gc)
    for name, handler, text in (
        ("worktree", cmd_worktree, "print the worktree holding the PR's stack, creating one if needed"),
        ("tick", cmd_tick, "tick Run B200 for the PR's head commit"),
        ("automerge", cmd_automerge, "enable squash auto-merge"),
    ):
        command = commands.add_parser(name, help=text)
        command.add_argument("pr", type=int)
        command.set_defaults(run=handler)
    close = commands.add_parser("close", help="close the PR, keeping its branch")
    close.add_argument("pr", type=int)
    close.add_argument("--note", required=True, help="why: stale or superseded")
    close.set_defaults(run=cmd_close)
    log = commands.add_parser("log", help="record what the sweep did to a PR")
    log.add_argument("action", choices=("rebase", "fix", "rerun", "needs-you"))
    log.add_argument("pr", type=int)
    log.add_argument("--blocks", choices=("rebase", "fix-ci", "tick-b200", "enable-automerge", "close"))
    log.add_argument("--note")
    log.set_defaults(run=cmd_log)
    args = parser.parse_args()
    args.run(args)


if __name__ == "__main__":
    main()
