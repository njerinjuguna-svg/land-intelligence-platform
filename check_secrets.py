r"""
============================================================================
WOULD PUSHING THIS PUBLISH A PASSWORD?
Land Intelligence Platform - Geocode Spatial Solutions Ltd

WHY THIS EXISTS

  03_etl/.env holds DB_PASSWORD in plain text and every script in this
  project reads it from there. .gitignore excludes it, which is correct and
  which is also a thing somebody has to have got right, once, in advance,
  and never undo. That is a reminder.

  This is the control. Run it before every push. It looks at what git would
  ACTUALLY publish - the tracked files, not the working tree - and refuses if
  a credential is among them.

  The asymmetry is the whole point. A password pushed to GitHub is public the
  moment it lands, and deleting the commit does not un-publish it: it is in
  forks, in caches, in anyone's clone. The only real remedy is to change the
  password everywhere it is used. Ten seconds of checking beats that.

WHAT IT LOOKS FOR

  - a .env file among the tracked files (the direct failure)
  - password / key / token / secret assignments with a real-looking value
  - live embed keys (pk_live_...)
  - private key blocks and AWS access key ids
  - connection strings carrying an inline password

  It deliberately ignores placeholders - put_your_password_here, <yours>,
  changeme, and anything interpolated at runtime like {pw} or os.getenv(...).
  A scanner that cries wolf on .env.example gets switched off within a week.

WHAT IT IS NOT

  It is not a guarantee. It knows the shapes of common secrets and nothing
  about a password that looks like an ordinary word. It cannot see history -
  if something was committed before this existed, `git log -p` is the only
  answer. Treat a pass as "no obvious credential", not as "safe".

USAGE
  python check_secrets.py            # tracked files, or the tree if no repo
  python check_secrets.py --all      # every file, ignoring git entirely
============================================================================
"""
import re
import sys
import subprocess
from pathlib import Path

BASE = Path(__file__).resolve().parent

# Mirrors .gitignore, for the case where no repository exists yet and there is
# no `git ls-files` to ask.
SKIP_DIRS = {"06_rasters", "venv", "__pycache__", ".git", "data",
             ".vscode", ".idea", "node_modules"}
SKIP_SUFFIX = {".dump", ".backup", ".gz", ".zip", ".tif", ".tiff", ".img",
               ".shp", ".dbf", ".shx", ".png", ".jpg", ".jpeg", ".pdf",
               ".xlsx", ".pyc", ".qgz", ".gpkg"}

# Assignments. Group 2 captures the opening quote, if any - see NEEDS_QUOTE.
ASSIGNMENTS = [
    (re.compile(r'(?i)\b(db_password|password|passwd|pwd)\s*[=:]\s*'
                r'(["\']?)([^\s"\';,#]{6,})'), "password assignment"),
    (re.compile(r'(?i)\b(api_key|apikey|secret|token|access_key|client_secret)'
                r'\s*[=:]\s*(["\']?)([^\s"\';,#]{8,})'), "key assignment"),
]

# Self-identifying. These are credentials whatever surrounds them.
LITERALS = [
    (re.compile(r'\bpk_live_[A-Za-z0-9_-]{6,}'), "live embed key"),
    (re.compile(r'-----BEGIN [A-Z ]*PRIVATE KEY-----'), "private key block"),
    (re.compile(r'\bAKIA[0-9A-Z]{16}\b'), "AWS access key id"),
    (re.compile(r'\bAIza[0-9A-Za-z_-]{30,}'), "Google API key"),
    (re.compile(r'postgres(?:ql)?(?:\+\w+)?://[^:\s/]+:[^@\s]+@'),
     "connection string with inline password"),
]

# IN SOURCE CODE, AN UNQUOTED VALUE CANNOT BE A CREDENTIAL.
#
# The first version of this flagged `api_key=x_api_key` in api_01_embed.py -
# a Python keyword argument passing a variable. It saw `api_key=` followed by
# eight characters and never asked whether those characters were a STRING.
#
# You cannot write an unquoted string literal in Python or JavaScript. So in
# these files a credential is necessarily quoted, and an unquoted value is an
# identifier, a number or an expression.
#
# In .env, .ini, .cfg and .yml the opposite holds: unquoted IS the normal way
# to write a value, and DB_PASSWORD=Nj3ri!Geocode2026 must still be caught.
# So the rule is per file type, not global - which is why a scanner that
# cried wolf on one line does not get "fixed" by loosening the pattern.
NEEDS_QUOTE = {".py", ".js", ".ts", ".jsx", ".tsx", ".mjs", ".java", ".rb",
               ".go", ".ps1", ".psm1", ".sql", ".c", ".cpp", ".cs", ".php",
               ".sh", ".bash", ".cmd", ".bat"}

# A value that is obviously not a real credential.
PLACEHOLDER = re.compile(
    r'(?i)^(put_your|your[_-]|my[_-]|<|\.\.\.|x{3,}|changeme|change[_-]me|'
    r'example|placeholder|password|passwd|secret|token|none|null|true|false|'
    r'localhost|postgres$|\d{1,5}$)')


def looks_interpolated(text):
    """{pw}, ${DB_PASSWORD}, os.getenv(...), %s - not a literal secret."""
    return any(m in text for m in ("{", "$", "getenv", "environ", "%s",
                                   "..."))


def scan_line(line, suffix=""):
    hits = []

    for rx, label in LITERALS:
        m = rx.search(line)
        if m and not looks_interpolated(m.group(0)):
            hits.append((label, m.group(0)))

    for rx, label in ASSIGNMENTS:
        m = rx.search(line)
        if not m:
            continue
        whole, quote, value = m.group(0), m.group(2), m.group(3)
        if looks_interpolated(whole):
            continue
        if not quote and suffix in NEEDS_QUOTE:
            continue                      # an identifier, not a string
        if PLACEHOLDER.match(value.strip("\"'")):
            continue
        hits.append((label, whole))

    return hits


def tracked_files():
    """What git would actually publish. Falls back to the working tree."""
    try:
        out = subprocess.run(["git", "ls-files"], cwd=BASE, text=True,
                             capture_output=True, timeout=30)
        if out.returncode == 0 and out.stdout.strip():
            return [BASE / p for p in out.stdout.splitlines()], True
    except (OSError, subprocess.SubprocessError):
        pass
    return None, False


def walk_tree():
    files = []
    for p in BASE.rglob("*"):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.suffix.lower() in SKIP_SUFFIX:
            continue
        files.append(p)
    return files


def main():
    scan_all = "--all" in sys.argv

    files, from_git = (None, False) if scan_all else tracked_files()
    if files is None:
        files = walk_tree()

    print("=" * 74)
    if from_git:
        print("SECRET CHECK - scanning the files GIT WOULD PUBLISH")
    else:
        print("SECRET CHECK - no repository yet, scanning the working tree")
        print("   (this is a preview: after `git init` it checks tracked "
              "files only)")
    print(f"   {len(files)} file(s)")
    print("=" * 74)

    env_tracked = [p for p in files
                   if p.name == ".env" or (p.suffix == ".env")]
    findings = []

    for p in files:
        if p.suffix.lower() in SKIP_SUFFIX or not p.exists():
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if len(text) > 4_000_000:
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if len(line) > 2000:
                continue
            for label, snippet in scan_line(line, p.suffix.lower()):
                findings.append((p, n, label, snippet.strip()[:110]))

    bad = False

    if env_tracked:
        bad = True
        print("\n*** A .env FILE IS IN THE PUBLISH SET ***\n")
        for p in env_tracked:
            print(f"      {p.relative_to(BASE)}")
        print("\n   This is the direct failure this check exists for.")
        print("   If it is not yet committed:  git rm --cached <file>")
        print("   If it is already pushed:     CHANGE THE PASSWORD. Removing")
        print("   the commit does not un-publish it.")

    if findings:
        bad = True
        print(f"\n*** {len(findings)} POSSIBLE CREDENTIAL(S) IN TRACKED "
              f"FILES ***\n")
        for p, n, label, snippet in findings:
            print(f"      {p.relative_to(BASE)}:{n}")
            print(f"         {label}: {snippet}")
        print("\n   Check each one. If any is real, remove it from the file,")
        print("   move it to .env, and change the credential itself - a value")
        print("   that has been in a pushed commit is spent.")

    print("\n" + "=" * 74)
    if bad:
        print("DO NOT PUSH until each item above is resolved.")
    else:
        print("No obvious credential in the publish set.")
        print()
        print("Not a guarantee. This knows the SHAPES of common secrets and")
        print("nothing about a password that looks like an ordinary word, and")
        print("it cannot see git history - only what is tracked now.")
    print("=" * 74)
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
