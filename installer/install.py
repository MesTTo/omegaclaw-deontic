#!/usr/bin/env python3
"""Install or remove the omegaclaw-deontic stack on a stock OmegaClaw-Core clone.

Two operations, kept strictly separate so the result is reversible:

  copy   the deontic files into the clone (all brand-new paths; nothing existing
         is overwritten on a clean clone).
  patch  the two core files that must change (lib_omegaclaw.metta and the
         getSkills catalogue in src/skills.metta), as managed blocks delimited
         by sentinel comments so a re-run replaces in place and uninstall strips
         them out.

An install writes a receipt (.omegaclaw-deontic-receipt.json) listing every file
copied and patch applied, so uninstall reverts exactly what was done.

Anchors are validated before anything is written: a missing anchor (upstream
restructured the file) aborts the whole install rather than leaving a half-patch.

Two managed-block shapes, because the two edits sit differently in their files:
  import-block    full lines inserted at a line boundary (lib_omegaclaw.metta).
  getskills-block inserted mid-structure, before the ')' that closes the
                  getSkills tuple, so it owns a leading and trailing newline to
                  keep that ')' on its own line and to revert byte-exactly.
"""

import argparse
import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

BUNDLE = Path(__file__).resolve().parent.parent
PAYLOAD = BUNDLE / "payload"
VERSION_FILE = BUNDLE / "VERSION"
RECEIPT_NAME = ".omegaclaw-deontic-receipt.json"
BAK_SUFFIX = ".omegaclaw-deontic.bak"

BEGIN = ";; >>> omegaclaw-deontic (managed; do not edit by hand) >>>"
END = ";; <<< omegaclaw-deontic <<<"
# Full inserted lines incl. trailing newline; revert leaves the line boundary intact.
IMPORT_BLOCK_RE = re.compile(r"[ \t]*;; >>> omegaclaw-deontic.*?;; <<< omegaclaw-deontic <<<\n", re.DOTALL)
# Leading + trailing newline are part of the span, so revert restores "X"))  exactly.
GETSKILLS_BLOCK_RE = re.compile(r"\n[ \t]*;; >>> omegaclaw-deontic.*?;; <<< omegaclaw-deontic <<<\n", re.DOTALL)

# Files whose import needs the faiss_ffi native build; off unless --enable-semantic.
SEMANTIC_FILES = {"src/integration/semantic.metta", "tests/integration/test_semantic.metta"}

# lib_omegaclaw.metta: the managed import block goes on the line after this anchor.
LIBOMEGA = "lib_omegaclaw.metta"
LIBOMEGA_ANCHOR = "!(import! &self (library OmegaClaw-Core lib_pln))"
LIBOMEGA_IMPORTS = [
    "!(import! &self (library OmegaClaw-Core lib_deontic))",
    "!(import! &self (library OmegaClaw-Core lib_directive))",
    "!(import! &self (library OmegaClaw-Core src/skills_deontic))",
    "!(import! &self (library OmegaClaw-Core src/policy_guard))",
    "!(import! &self (library OmegaClaw-Core src/integration/nal))",
]
# Appended only with --enable-semantic, so enabling the layer is self-contained:
# it pulls and builds faiss_ffi itself before importing the semantic module.
SEMANTIC_IMPORTS = [
    '!(git-import! "https://github.com/patham9/faiss_ffi" "build.sh")',
    "!(import! &self (library OmegaClaw-Core src/integration/semantic))",
]

# src/skills.metta: catalogue lines spliced into the getSkills tuple.
SKILLS = "src/skills.metta"
GETSKILLS_LINES = [
    '"- Defeasible + deontic reasoning over a theory file (tagged conclusions): deontic-conclude path"',
    '"- Conclusions under Standard Deontic Logic closure (O/P/F, F p = O not p): deontic-norms path"',
    '"- Detect unresolved deontic dilemmas (O p and O not p both applicable): deontic-conflicts path"',
    '"- Next actionable tasks in a directive plan file: directive-next path"',
    '"- Task status groups (ready/blocked/claimed/done) of a plan file: directive-status path"',
    '"- Kanban board view of a directive plan file: directive-board path"',
    '"- One-line progress summary of a directive plan file: directive-summary path"',
]

# src/loop.metta: route skill dispatch through the guard (only --enable-guardrail).
LOOP = "src/loop.metta"
LOOP_PLAIN = "(catch (let $R (eval $s) (py-call (helper.normalize_string $R)))"
LOOP_GUARDED = "(catch (let $R (guarded-eval $s) (py-call (helper.normalize_string $R)))"


def bundle_version():
    try:
        return VERSION_FILE.read_text().strip()
    except OSError:
        return "0.0.0"


def die(msg):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(1)


def find_getskills_close(text):
    """Index of the ')' that closes the getSkills tuple, i.e. where to splice new
    catalogue elements. Paren-balanced scan that ignores strings and ; comments,
    so it survives upstream edits to the surrounding skills."""
    m = re.search(r"\(=\s*\(getSkills\)", text)
    if not m:
        return None
    i = m.end()           # just past "(= (getSkills)"; we are at depth 1
    depth = 1
    in_str = in_comment = False
    n = len(text)
    while i < n:
        c = text[i]
        if in_comment:
            if c == "\n":
                in_comment = False
            i += 1
        elif in_str:
            if c == "\\":
                i += 2
            else:
                if c == '"':
                    in_str = False
                i += 1
        elif c == '"':
            in_str = True
            i += 1
        elif c == ";":
            in_comment = True
            i += 1
        elif c == "(":
            depth += 1
            i += 1
        elif c == ")":
            depth -= 1
            if depth == 1:
                return i      # closes the tuple (depth 2 -> 1)
            if depth == 0:
                return None   # equation closed before a tuple: unexpected shape
            i += 1
        else:
            i += 1
    return None


def strip_import_block(text):
    return IMPORT_BLOCK_RE.sub("", text)


def strip_getskills_block(text):
    return GETSKILLS_BLOCK_RE.sub("", text)


def import_block(imports):
    body = "\n".join(imports)
    return f"{BEGIN}\n{body}\n{END}\n"


def getskills_block(lines):
    indent = "    "
    body = "\n".join(indent + ln for ln in lines)
    return f"\n{indent}{BEGIN}\n{body}\n{indent}{END}\n"


def patch_libomega(text, enable_semantic):
    if LIBOMEGA_ANCHOR not in text:
        return None
    text = strip_import_block(text)
    imports = LIBOMEGA_IMPORTS + (SEMANTIC_IMPORTS if enable_semantic else [])
    idx = text.index(LIBOMEGA_ANCHOR)
    eol = text.index("\n", idx) + 1           # start of the line after the anchor
    return text[:eol] + import_block(imports) + text[eol:]


def patch_getskills(text):
    text = strip_getskills_block(text)
    close = find_getskills_close(text)
    if close is None:
        return None
    return text[:close] + getskills_block(GETSKILLS_LINES) + text[close:]


def patch_loop_enable(text):
    if LOOP_GUARDED in text:
        return text          # already routed
    if LOOP_PLAIN not in text:
        return None
    return text.replace(LOOP_PLAIN, LOOP_GUARDED, 1)


def patch_loop_disable(text):
    return text.replace(LOOP_GUARDED, LOOP_PLAIN, 1)


def selected_files(enable_semantic, minimal):
    for src in sorted(p for p in PAYLOAD.rglob("*") if p.is_file()):
        rel = src.relative_to(PAYLOAD).as_posix()
        if rel in SEMANTIC_FILES and not enable_semantic:
            continue
        if minimal and (rel.startswith("tests/") or rel.startswith("docs/")):
            continue
        yield rel, src


def load_receipt(target):
    p = target / RECEIPT_NAME
    if p.exists():
        return json.loads(p.read_text())
    return None


def backup(target, rel, receipt_backups):
    """Snapshot the pristine file once; always record it in the receipt so an
    idempotent re-run does not lose track of an earlier backup."""
    bak = target / (rel + BAK_SUFFIX)
    if not bak.exists():
        shutil.copy2(target / rel, bak)
    if (rel + BAK_SUFFIX) not in receipt_backups:
        receipt_backups.append(rel + BAK_SUFFIX)


def do_install(target, enable_semantic, enable_guardrail, minimal, force, dry):
    if not (target / LIBOMEGA).exists() or not (target / SKILLS).exists():
        die(f"{target} does not look like an OmegaClaw-Core clone "
            f"(missing {LIBOMEGA} or {SKILLS}).")

    prior = load_receipt(target)
    prior_files = set(prior["copied_files"]) if prior else set()

    files = list(selected_files(enable_semantic, minimal))

    # Validation pass: anchors must resolve and copies must not clobber foreign files.
    libomega_text = (target / LIBOMEGA).read_text()
    if patch_libomega(libomega_text, enable_semantic) is None:
        die(f"{LIBOMEGA}: import anchor not found:\n  {LIBOMEGA_ANCHOR}")
    skills_text = (target / SKILLS).read_text()
    if patch_getskills(skills_text) is None:
        die(f"{SKILLS}: could not locate the getSkills tuple to splice into.")
    loop_text = None
    if enable_guardrail:
        loop_text = (target / LOOP).read_text()
        if patch_loop_enable(loop_text) is None:
            die(f"{LOOP}: guard anchor not found:\n  {LOOP_PLAIN}")
    for rel, _ in files:
        dst = target / rel
        if dst.exists() and rel not in prior_files and not force:
            die(f"refusing to overwrite existing file not from a prior install: {rel}\n"
                f"  (re-run with --force to overwrite)")

    print(f"omegaclaw-deontic {bundle_version()} -> {target}")
    print(f"  layers: core, directive, skill, nal, guardrail"
          f"{', semantic' if enable_semantic else ''}"
          f"{' (guard loop routing ON)' if enable_guardrail else ''}")
    print(f"  copy {len(files)} files; patch {LIBOMEGA}, {SKILLS}"
          f"{', ' + LOOP if enable_guardrail else ''}")
    if dry:
        print("  (dry run: nothing written)")
        return

    receipt = {
        "bundle_version": bundle_version(),
        "installed_at": datetime.now(timezone.utc).isoformat(),
        "target": str(target),
        "flags": {"semantic": enable_semantic, "guardrail": enable_guardrail,
                  "minimal": minimal},
        "copied_files": [],
        "patched_files": [],
        "backups": [],
    }

    for rel, src in files:
        dst = target / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        receipt["copied_files"].append(rel)

    backup(target, LIBOMEGA, receipt["backups"])
    (target / LIBOMEGA).write_text(patch_libomega(libomega_text, enable_semantic))
    receipt["patched_files"].append({"path": LIBOMEGA, "kind": "import-block"})

    backup(target, SKILLS, receipt["backups"])
    (target / SKILLS).write_text(patch_getskills(skills_text))
    receipt["patched_files"].append({"path": SKILLS, "kind": "getskills-block"})

    if enable_guardrail:
        backup(target, LOOP, receipt["backups"])
        (target / LOOP).write_text(patch_loop_enable(loop_text))
        receipt["patched_files"].append({"path": LOOP, "kind": "guard-route"})

    (target / RECEIPT_NAME).write_text(json.dumps(receipt, indent=2))
    print(f"  done. receipt: {target / RECEIPT_NAME}")
    if enable_semantic:
        print("  note: the semantic layer triggers a faiss_ffi git clone + build "
              "on first run (needs network and a C/C++ toolchain).")


def prune_empty_dirs(target, rels):
    dirs = sorted({(target / rel).parent for rel in rels},
                  key=lambda p: len(p.parts), reverse=True)
    for d in dirs:
        try:
            while d != target and d.is_dir() and not any(d.iterdir()):
                d.rmdir()
                d = d.parent
        except OSError:
            pass


def unpatch(target, entry):
    f = target / entry["path"]
    if not f.exists():
        return
    kind = entry["kind"]
    if kind == "guard-route":
        f.write_text(patch_loop_disable(f.read_text()))
    elif kind == "import-block":
        f.write_text(strip_import_block(f.read_text()))
    elif kind == "getskills-block":
        f.write_text(strip_getskills_block(f.read_text()))


def do_uninstall(target, dry):
    receipt = load_receipt(target)
    if not receipt:
        print(f"no receipt at {target}; stripping managed blocks best-effort.")
        if not dry:
            fo = target / LIBOMEGA
            if fo.exists():
                fo.write_text(strip_import_block(fo.read_text()))
            fs = target / SKILLS
            if fs.exists():
                fs.write_text(strip_getskills_block(fs.read_text()))
            fl = target / LOOP
            if fl.exists():
                fl.write_text(patch_loop_disable(fl.read_text()))
        return

    print(f"removing omegaclaw-deontic {receipt.get('bundle_version','?')} from {target}")
    if dry:
        print(f"  would remove {len(receipt['copied_files'])} files and "
              f"un-patch {len(receipt['patched_files'])} files")
        return

    for entry in receipt["patched_files"]:
        unpatch(target, entry)

    for rel in receipt["copied_files"]:
        f = target / rel
        if f.exists():
            f.unlink()
    prune_empty_dirs(target, receipt["copied_files"])

    for bak in receipt["backups"]:
        b = target / bak
        if b.exists():
            b.unlink()

    (target / RECEIPT_NAME).unlink(missing_ok=True)
    print("  done. clone restored to its pre-install state.")


def main():
    ap = argparse.ArgumentParser(
        description="Install/remove the omegaclaw-deontic stack on an OmegaClaw-Core clone.")
    ap.add_argument("target", type=Path,
                    help="path to the OmegaClaw-Core clone (the dir with lib_omegaclaw.metta)")
    ap.add_argument("--uninstall", action="store_true", help="revert a previous install")
    ap.add_argument("--enable-semantic", action="store_true",
                    help="also enable the FAISS semantic layer (pulls + builds faiss_ffi)")
    ap.add_argument("--enable-guardrail", action="store_true",
                    help="route the agent loop through the deontic guard (inert until a policy is set)")
    ap.add_argument("--minimal", action="store_true", help="skip tests/ and docs/ (for images)")
    ap.add_argument("--force", action="store_true", help="overwrite existing files")
    ap.add_argument("--dry-run", action="store_true", help="show the plan, write nothing")
    args = ap.parse_args()

    target = args.target.resolve()
    if not target.is_dir():
        die(f"target not a directory: {target}")
    if not PAYLOAD.is_dir():
        die(f"bundle payload missing: {PAYLOAD}")

    if args.uninstall:
        do_uninstall(target, args.dry_run)
    else:
        do_install(target, args.enable_semantic, args.enable_guardrail,
                   args.minimal, args.force, args.dry_run)


if __name__ == "__main__":
    main()
