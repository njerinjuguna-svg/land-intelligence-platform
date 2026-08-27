r"""
============================================================================
PATCH - make every ETL log its own failure
Land Intelligence Platform - Geocode Spatial Solutions Ltd

THE BUG
  Every ETL in this folder wraps its work in

      except Exception as exc:
          ... UPDATE metadata.etl_runs SET run_status = 'failed' ...
          raise

  and every ETL's own safety guards raise SystemExit:

      raise SystemExit("Empty Kenya window in the native grid.")

  SystemExit inherits from BaseException, NOT from Exception. So it sails
  straight past that handler and the run row is never closed. KeyboardInterrupt
  (Ctrl+C) does the same.

  The result is exactly backwards: a script that crashes on a bug it did not
  anticipate logs the failure correctly, while a script stopped by a guard it
  deliberately wrote does not. THE CAREFUL PATH IS THE ONE THAT LIES.

  Measured cost: 12 rows sat at run_status = 'running', the oldest for a
  month, while PROGRESS.md recorded those same runs as failures. Run 52 is
  documented as "RUN 52 FAILED AND THE FAILURE WAS THE POINT" and the
  database still said it was running.

THE FIX
  except Exception  ->  except BaseException

  The trailing `raise` in every handler is unchanged, so Ctrl+C still
  interrupts and sys.exit() still exits with its message. The only difference
  is that the run row is closed on the way out.

  Guards get run_status 'failed'. A KeyboardInterrupt is recorded as
  'failed' too, with a message saying it was interrupted, because 'partial'
  in this schema means "finished with some rows rejected", not "stopped
  halfway".

WHY A SCRIPT AND NOT 29 HAND EDITS
  The change is identical in all 29 files. A script is reviewable in one
  place, idempotent, and reports exactly what it touched. Hand-editing 29
  files is 29 chances to typo something into a pipeline that currently works.

  It writes a .bak beside each file it changes. Nothing is edited in place
  without a copy.

How to run (from 03_etl):
  python patch_etl_failure_logging.py --dry-run     <- always do this first
  python patch_etl_failure_logging.py
============================================================================
"""

import sys
import shutil
from pathlib import Path

BASE = Path(__file__).resolve().parent

OLD = "except Exception as exc:"
NEW = "except BaseException as exc:"

# The comment dropped in above the handler, so the next person to read the
# file knows why it is BaseException and does not "tidy" it back.
NOTE_LINES = [
    "# BaseException, NOT Exception, and this is load-bearing.",
    "# This script's own guards raise SystemExit, and Ctrl+C raises",
    "# KeyboardInterrupt. Both inherit from BaseException, so an",
    "# `except Exception` handler never fires for them and the",
    "# metadata.etl_runs row is left at 'running' forever. That bug left 12",
    "# orphan rows across a month of work, including runs PROGRESS.md",
    "# documents as failures. The trailing `raise` is unchanged: this logs",
    "# the failure and then gets out of the way.",
]


def patch(path: Path, dry: bool):
    src = path.read_text(encoding="utf-8")

    if NEW in src:
        return "already patched", 0
    if OLD not in src:
        return "no run-logging handler", 0

    lines = src.split("\n")
    out, n = [], 0
    for line in lines:
        stripped = line.strip()
        if stripped == OLD:
            indent = line[:len(line) - len(line.lstrip())]
            for c in NOTE_LINES:
                out.append(indent + c)
            out.append(indent + NEW)
            n += 1
        else:
            out.append(line)

    if n == 0:
        # The handler exists but not on a line of its own, so the safe
        # automatic edit is not available. Report it rather than guess.
        return "handler found but not on its own line - EDIT BY HAND", 0

    if not dry:
        shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))
        path.write_text("\n".join(out), encoding="utf-8")

    return f"patched {n} handler(s)", n


def main():
    dry = "--dry-run" in sys.argv

    # Only this project's ETL and verify scripts. Never the venv.
    targets = sorted(
        p for p in BASE.glob("*.py")
        if p.name != Path(__file__).name and "venv" not in p.parts
    )

    print("PATCH: except Exception -> except BaseException in run-logging "
          "handlers")
    print(f"Folder: {BASE}")
    print(f"Mode  : {'DRY RUN, nothing will be written' if dry else 'WRITING (.bak kept beside each file)'}")
    print("-" * 74)

    changed = manual = 0
    for p in targets:
        status, n = patch(p, dry)
        if n:
            changed += 1
            print(f"  {p.name:38} {status}")
        elif "EDIT BY HAND" in status:
            manual += 1
            print(f"  {p.name:38} *** {status} ***")

    print("-" * 74)
    print(f"{changed} file(s) {'would be' if dry else ''} patched, "
          f"{manual} need manual attention, "
          f"{len(targets)-changed-manual} unaffected.")

    if dry:
        print("\nDry run only. Re-run without --dry-run to apply.")
    else:
        print("\nDone. Verify before trusting it:")
        print("  python -m py_compile *.py")
        print("\nThen prove it works, because a fix you have not seen fire is")
        print("a hope. Start any ETL and press Ctrl+C during the download,")
        print("then check the row closed itself:")
        print("  SELECT run_id, pipeline, run_status, error_message")
        print("  FROM metadata.etl_runs ORDER BY run_id DESC LIMIT 1;")
        print("\nExpect run_status = 'failed', NOT 'running'.")
        print("\nRemove the .bak files once you are satisfied:")
        print("  Remove-Item *.py.bak")


if __name__ == "__main__":
    main()
