#!/usr/bin/env python3
"""
Generates backdated git commits that spell "HELLO WORLD" in GitHub's
contribution graph with a left-to-right gradient: H is dimmest (1 commit),
D is brightest (10 commits), each letter a step darker.

Usage:
  python generate_commits.py             # add any missing commits
  python generate_commits.py --dry-run   # preview without committing
  python generate_commits.py --preview   # show shaded pattern and exit
  python generate_commits.py --reset     # wipe history and regenerate cleanly
                                         # (then: git push -f origin main)
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

TEXT       = "HELLO WORLD"
ROW_OFFSET = 1        # Mon = row 1 in GitHub graph (Sun=0 … Sat=6)
MSG_PREFIX = "HWART"

MIN_COMMITS = 1       # H (leftmost letter)
MAX_COMMITS = 10      # D (rightmost letter)
PAT_START   = 1       # first lit column in the 52-col pattern
PAT_END     = 51      # last  lit column


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


def grid_start(today):
    days_since_sun = (today.weekday() + 1) % 7
    this_sun = today - timedelta(days=days_since_sun)
    return this_sun - timedelta(weeks=52)


def col_commits(w):
    """Gradient commit count for column w (MIN at PAT_START, MAX at PAT_END)."""
    t = max(0.0, min(1.0, (w - PAT_START) / (PAT_END - PAT_START)))
    return max(MIN_COMMITS, round(MIN_COMMITS + (MAX_COMMITS - MIN_COMMITS) * t))


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
                    result[target_date] = col_commits(w)
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


def do_reset():
    """Save scripts → orphan branch → wipe → restore scripts."""
    script_file   = os.path.abspath(__file__)
    repo_root     = os.path.dirname(script_file)
    workflow_file = os.path.join(repo_root, ".github", "workflows", "maintain-pattern.yml")

    tmp = tempfile.mkdtemp()
    shutil.copy2(script_file, os.path.join(tmp, "generate_commits.py"))
    if os.path.exists(workflow_file):
        os.makedirs(os.path.join(tmp, ".github", "workflows"))
        shutil.copy2(workflow_file,
                     os.path.join(tmp, ".github", "workflows", "maintain-pattern.yml"))

    subprocess.run(["git", "checkout", "--orphan", "_art_reset"], check=True)
    subprocess.run(["git", "rm", "-rf", "."], capture_output=True)

    shutil.copy2(os.path.join(tmp, "generate_commits.py"), "generate_commits.py")
    wf_src = os.path.join(tmp, ".github", "workflows", "maintain-pattern.yml")
    if os.path.exists(wf_src):
        os.makedirs(".github/workflows", exist_ok=True)
        shutil.copy2(wf_src, ".github/workflows/maintain-pattern.yml")

    shutil.rmtree(tmp)
    print("Wiped history → orphan branch '_art_reset'")


def print_preview(today):
    cols       = build_columns()
    day_labels = "SMTWTFS"
    shades     = '░▒▓█'

    def shade_char(w, on):
        if not on:
            return '·'
        n     = col_commits(w)
        level = min(3, (n - 1) * 4 // MAX_COMMITS)
        return shades[level]

    print(f"\n  Gradient HELLO WORLD  "
          f"(░ = {MIN_COMMITS} commit  →  █ = {MAX_COMMITS} commits,  H dim → D bright)\n")
    for row in range(7):
        cells  = "".join(shade_char(w, col[row]) for w, col in enumerate(cols))
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

    if reset and not dry:
        do_reset()

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
