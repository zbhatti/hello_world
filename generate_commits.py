#!/usr/bin/env python3
"""
Generates backdated git commits that spell "HELLO WORLD" in GitHub's
contribution graph as plain, uniformly-colored text (every lit cell gets
the same commit count).

Usage:
  python generate_commits.py             # add any missing commits
  python generate_commits.py --dry-run   # preview without committing
  python generate_commits.py --preview   # show shaded pattern and exit
  python generate_commits.py --reset     # wipe history and regenerate cleanly
                                         # (then: git push -f origin main)
                                         # refused if a prior reset is on
                                         # record; add --force-reset to
                                         # override (see check_reset_allowed)
"""
import subprocess, sys, os, shutil, tempfile
from datetime import date, timedelta

FONT = {
    'H': [[1,0,0,1],[1,0,0,1],[1,1,1,1],[1,0,0,1],[1,0,0,1]],
    'E': [[1,1,1,1],[1,0,0,0],[1,1,1,0],[1,0,0,0],[1,1,1,1]],
    'L': [[1,0,0,0],[1,0,0,0],[1,0,0,0],[1,0,0,0],[1,1,1,1]],
    'O': [[0,1,1,0],[1,0,0,1],[1,0,0,1],[1,0,0,1],[0,1,1,0]],
    'W': [[1,0,0,0,1],[1,0,1,0,1],[1,0,1,0,1],[1,1,0,1,1],[1,0,0,0,1]],
    'R': [[1,1,1,0],[1,0,0,1],[1,1,1,0],[1,0,1,0],[1,0,0,1]],
    'D': [[1,1,1,0],[1,0,0,1],[1,0,0,1],[1,0,0,1],[1,1,1,0]],
}

TEXT         = "HELLO WORLD"
ROW_OFFSET   = 1        # Mon = row 1 in GitHub graph (Sun=0 … Sat=6)
MSG_PREFIX   = "HWART"
RESET_MARKER = ".art_reset_history"   # records every reset; committed to the repo
EPOCH_FILE   = ".art_epoch"           # pins the pattern to fixed calendar dates

COMMITS_PER_CELL = 6   # flat commit count for every lit cell (solid, dark green)


def build_columns():
    cols = [[0]*7]    # 1-col left margin
    chars = list(TEXT)
    for i, ch in enumerate(chars):
        if ch == ' ':
            cols += [[0]*7, [0]*7]
            continue
        letter = FONT[ch]
        for c in range(len(letter[0])):
            col = [0]*7
            for r in range(5):
                col[r + ROW_OFFSET] = letter[r][c]
            cols.append(col)
        if i < len(chars) - 1 and chars[i + 1] != ' ':
            cols.append([0]*7)
    return cols


def compute_epoch(today):
    """The Sunday that anchors column 0, computed fresh relative to `today`."""
    days_since_sun = (today.weekday() + 1) % 7
    this_sun = today - timedelta(days=days_since_sun)
    return this_sun - timedelta(weeks=52)


def grid_start(today):
    """Anchor for column 0. Reads the pinned epoch from EPOCH_FILE so the
    pattern's calendar dates stay fixed across runs.

    Without this, grid_start recomputed "52 weeks before today" on every
    run, which shifts EVERY column's target date each time today advances.
    A weekly cron run then finds ~70% of cells no longer match any existing
    commit and creates a full new round of commits at the shifted dates on
    top of the old ones — unbounded growth, forever. Pinning the epoch once
    means later runs only fill in columns that are newly due (their target
    date becomes <= today) instead of replaying the whole pattern at new
    dates.
    """
    if os.path.exists(EPOCH_FILE):
        with open(EPOCH_FILE) as f:
            return date.fromisoformat(f.read().strip())
    return compute_epoch(today)


def needed_with_targets(today):
    """Return {date: target_commit_count} for all lit cells."""
    cols  = build_columns()
    start = grid_start(today)
    result = {}
    for w, col in enumerate(cols):
        for d, on in enumerate(col):
            if on:
                target_date = start + timedelta(weeks=w, days=d)
                if target_date <= today:
                    result[target_date] = COMMITS_PER_CELL
    return result


def committed_date_counts():
    """Return {date: commit_count} for every HWART commit in the log."""
    out = subprocess.run(
        ["git", "log", "--format=%aI", f"--grep={MSG_PREFIX}"],
        capture_output=True, text=True
    ).stdout
    counts = {}
    for line in out.splitlines():
        try:
            d = date.fromisoformat(line[:10])
            counts[d] = counts.get(d, 0) + 1
        except ValueError:
            pass
    return counts


def make_commit(d, index=1):
    ds   = d.isoformat()
    hour = min(9 + index, 22)
    ts   = f"{ds}T{hour:02d}:00:00+00:00"
    with open("contribution.txt", "w") as f:
        f.write(f"{ds} {index}\n")
    env = {**os.environ, "GIT_AUTHOR_DATE": ts, "GIT_COMMITTER_DATE": ts}
    subprocess.run(["git", "add", "contribution.txt"], check=True)
    subprocess.run(
        ["git", "commit", "-m", f"{MSG_PREFIX}: HELLO WORLD {ds} ({index})"],
        env=env, check=True
    )


def prior_resets():
    """Return list of ISO timestamps of past resets, read from the marker file."""
    if not os.path.exists(RESET_MARKER):
        return []
    with open(RESET_MARKER) as f:
        return [line.strip() for line in f if line.strip()]


def check_reset_allowed(force):
    """Refuse to reset again unless --force-reset is given.

    A --reset force-pushes rewritten history. GitHub's contribution graph
    and commit search index do NOT forget commits just because they became
    unreachable — every prior reset leaves a permanent "ghost" layer of
    contributions at whatever calendar alignment that run used, which
    accumulates into noise that drowns out the letters. See README/commit
    history for the incident this guarded against.
    """
    past = prior_resets()
    if not past:
        return True
    if force:
        return True
    print(f"\nRefusing to --reset: {len(past)} prior reset(s) on record "
          f"(most recent {past[-1]}).")
    print("Each reset permanently pollutes the GitHub contribution graph with")
    print("ghost commits that GitHub keeps counting even after the history")
    print("that contained them is force-pushed away. Re-run with both")
    print("--reset --force-reset if you are certain you want another one —")
    print("ideally only after recreating the GitHub repo from scratch so the")
    print("old ghost contributions are actually gone.\n")
    return False


def do_reset(today):
    """Save scripts → orphan branch → wipe → restore scripts."""
    script_file   = os.path.abspath(__file__)
    repo_root     = os.path.dirname(script_file)
    workflow_file = os.path.join(repo_root, ".github", "workflows", "maintain-pattern.yml")
    marker_file   = os.path.join(repo_root, RESET_MARKER)

    tmp = tempfile.mkdtemp()
    shutil.copy2(script_file, os.path.join(tmp, "generate_commits.py"))
    if os.path.exists(workflow_file):
        os.makedirs(os.path.join(tmp, ".github", "workflows"))
        shutil.copy2(workflow_file,
                     os.path.join(tmp, ".github", "workflows", "maintain-pattern.yml"))
    past = prior_resets()
    if os.path.exists(marker_file):
        shutil.copy2(marker_file, os.path.join(tmp, RESET_MARKER))

    subprocess.run(["git", "checkout", "--orphan", "_art_reset"], check=True)
    subprocess.run(["git", "rm", "-rf", "."], capture_output=True)

    shutil.copy2(os.path.join(tmp, "generate_commits.py"), "generate_commits.py")
    wf_src = os.path.join(tmp, ".github", "workflows", "maintain-pattern.yml")
    if os.path.exists(wf_src):
        os.makedirs(".github/workflows", exist_ok=True)
        shutil.copy2(wf_src, ".github/workflows/maintain-pattern.yml")

    with open(RESET_MARKER, "w") as f:
        for ts in past:
            f.write(ts + "\n")
        f.write(date.today().isoformat() + "T00:00:00\n")

    # Pin a fresh epoch so the pattern's calendar dates are fixed from here
    # on — subsequent runs (including the weekly cron) must not shift them.
    with open(EPOCH_FILE, "w") as f:
        f.write(compute_epoch(today).isoformat() + "\n")

    shutil.rmtree(tmp)
    print("Wiped history → orphan branch '_art_reset'")


def print_preview(today):
    cols       = build_columns()
    day_labels = "SMTWTFS"

    def shade_char(on):
        return '█' if on else '·'

    print(f"\n  HELLO WORLD  ({COMMITS_PER_CELL} commits per lit cell, flat)\n")
    for row in range(7):
        cells  = "".join(shade_char(col[row]) for col in cols)
        cells += '·' * (53 - len(cols))
        print(f"  {day_labels[row]}  {cells}")
    print()


def main():
    dry          = "--dry-run" in sys.argv
    preview_only = "--preview" in sys.argv
    reset        = "--reset"   in sys.argv
    today        = date.today()

    print_preview(today)
    if preview_only:
        return

    force_reset = "--force-reset" in sys.argv

    if reset and not dry:
        if not check_reset_allowed(force_reset):
            sys.exit(1)
        do_reset(today)

    targets  = needed_with_targets(today)
    existing = committed_date_counts()

    total_have    = sum(min(existing.get(d, 0), t) for d, t in targets.items())
    total_need    = sum(targets.values())
    total_missing = total_need - total_have

    print(f"Lit cells           : {len(targets)}")
    print(f"Total commits target: {total_need}")
    print(f"Already committed   : {total_have}")
    print(f"Commits to create   : {total_missing}")

    if total_missing == 0:
        print("\nNothing to do — pattern is complete.")
        return

    for d in sorted(targets):
        target  = targets[d]
        current = existing.get(d, 0)
        for i in range(current, target):
            if dry:
                print(f"  [dry-run] {d}  commit {i+1}/{target}")
            else:
                print(f"  {d}  commit {i+1}/{target} …")
                make_commit(d, index=i+1)

    if not dry:
        print(f"\nCreated {total_missing} commit(s).")
        if reset:
            first_date = min(targets)
            ts  = f"{first_date.isoformat()}T09:00:00+00:00"
            env = {**os.environ, "GIT_AUTHOR_DATE": ts, "GIT_COMMITTER_DATE": ts}
            subprocess.run(["git", "add", "generate_commits.py"], check=True)
            if os.path.exists(".github"):
                subprocess.run(["git", "add", ".github"], check=True)
            if os.path.exists(RESET_MARKER):
                subprocess.run(["git", "add", RESET_MARKER], check=True)
            if os.path.exists(EPOCH_FILE):
                subprocess.run(["git", "add", EPOCH_FILE], check=True)
            subprocess.run(
                ["git", "commit", "-m", "Add contribution art scripts"],
                env=env, check=True
            )
            subprocess.run(["git", "branch", "-D", "main"], capture_output=True)
            subprocess.run(["git", "branch", "-m", "_art_reset", "main"], check=True)
            print("Force push with:  git push -f origin main")
        else:
            print("Push with:  git push origin main")


if __name__ == "__main__":
    main()
