# Design notes

## The problem

OmegaClaw-Core has a skill system and documented extension points, but "add a
skill" is two manual edits to core files: import the library in
`lib_omegaclaw.metta`, and splice a catalogue line into `getSkills` in
`src/skills.metta`. The deontic stack is many files plus exactly those two edits.
To let a third party add it without hand-editing core, the work is to automate
those two edits reversibly while copying the rest in.

`getSkills` is the constraint that rules out a pure no-touch plugin. It is a single
closed list, read once and concatenated straight into the LLM prompt
(`src/loop.metta`), so it must stay single-valued. A second `getSkills` equation
would make it non-deterministic and break the prompt. The catalogue line has to go
*into* that one list.

## Why an installer

Of the delivery options (a git-imported plugin repo, an installer onto a stock
clone, or an upstream plugin-loader seam), this bundle takes the installer route. It
works on a frozen upstream with no cooperation and no new core machinery, and it
stays reversible. The trade is that it edits two core files in place rather than
discovering the plugin at load time. A registry refactor of `getSkills` (fold over a
`(skill-doc)` set) makes future plugins zero-edit. It was proposed upstream and not
merged, so the installer offers it as the opt-in `--skill-registry` mode rather than
forcing it: the default stays the minimal splice, and a user who wants the open
catalogue chooses it. See below.

## Mechanism

The install is two separate operations so the result is reversible:

- **Copy** the deontic files into the clone. On a clean clone these are all new
  paths, so nothing existing is touched. A refusal guards against clobbering a
  foreign file that is not from a prior install (override with `--force`).
- **Patch** the two core files as managed blocks delimited by sentinel comments
  (`;; >>> omegaclaw-deontic ... >>>` / `;; <<< ... <<<`). A re-run strips the old
  block and re-inserts, so installs are idempotent; uninstall strips the block out.

The two edits sit differently in their files, so the managed block has two shapes:

- `lib_omegaclaw.metta`: full lines inserted at the line after the `lib_pln` import
  anchor. Reverting removes the lines and leaves the line boundary intact.
- `src/skills.metta`: the catalogue lines go *inside* the `getSkills` tuple, before
  the `)` that closes it. That close sits mid-line (`"...last..."))`), so the
  inserted span owns a leading and a trailing newline; this keeps the `)` on its own
  line and lets uninstall restore the original `"...last..."))` byte-for-byte. The
  insertion point is found by a paren-balanced scan that ignores strings and `;`
  comments, so it survives upstream edits to the surrounding skills.

Reversibility is receipt-driven. An install writes
`.omegaclaw-deontic-receipt.json` listing every file copied, every patch applied
(with its kind), and the backups taken. Uninstall replays that receipt: un-patch by
kind, delete copied files, prune now-empty directories, drop the backups and the
receipt. Anchors are validated in a dry pass before any write, so a missing anchor
aborts cleanly instead of leaving a half-patch.

## Layer posture, and three engineering calls

The bundle ships all six layers, but three of them needed a judgment call so a
default install is safe:

- **Semantic is gated.** `src/integration/semantic.metta` imports `faiss_ffi`, a
  native FAISS binding built by its own `build.sh`. Importing it unconditionally
  would fail agent startup wherever `faiss_ffi` is absent. So its import is off
  unless `--enable-semantic`, which also wires the `git-import!` + build so the layer
  is self-contained.
- **The guardrail's loop route is opt-in.** `policy_guard.metta` is always copied and
  imported (it only defines `guarded-eval` and the verdict functions, inert on its
  own). The one edit to the hot loop, routing `(eval $s)` through `guarded-eval`, is
  applied only with `--enable-guardrail`, and even then stays inert until
  `deonticGuardEnabled` and a policy are set.
- **Directive read-views are advertised as skills.** On the upstream branches the
  directive layer was a CLI, not an agent skill. Its read-only views
  (`directive-next/status/board/summary`) are single-argument and safe, so the bundle
  advertises them. The fuller lifecycle surface stays available programmatically.

## The optional skill-doc registry

`--skill-registry` applies the open-catalogue refactor instead of the splice. It
rewrites the closed `getSkills` into

```metta
(= (skill-doc) (superpose (;INTERNAL: ...core lines...)))
(= (getSkills) (collapse (skill-doc)))
```

so `getSkills` collects every `(skill-doc)` result, and registers each deontic skill
as its own `(= (skill-doc) "...")` equation. `superpose`/`collapse` keep `getSkills`
single-valued and, with no extra equations, byte-identical to the original (verified
by rendering both under PeTTa). Because the refactor is structural rather than a
managed block, uninstall reverts it by restoring the pristine `skills.metta` backup
recorded in the receipt. The default install is unaffected; this is purely opt-in.

## Docker

The prebuilt image bakes the clone at `/PeTTa/repos/OmegaClaw-Core`. The overlay runs
the same installer at build time (`--minimal`, so tests and docs are skipped), which
keeps the runtime posture untouched (the entrypoint still drops to `nobody` with
tmpfs and a scrubbed environment). Users select the overlay image with the launcher's
existing `-d` flag, so no launcher change is needed.

## Verification

- Deontic golden suite: 10 files, 93 checks, all pass under SWI-Prolog 9.2.9, run
  from a freshly installed stock clone (`origin/main` at `519c342`).
- Installer surgery: clean install, idempotent re-run (one managed block, never two),
  and `--uninstall` restoring `lib_omegaclaw.metta`, `src/skills.metta`, and
  `src/loop.metta` to byte-identical, with a clean `git status`. Verified for the
  default, `--enable-guardrail`, and `--enable-semantic` cycles.
- Full-stack smoke from the installed clone: `deontic-conclude` returns the correct
  penguin conclusion set under both the `dl-path` form and the real
  `(deontic-conclude "path")` quoted-string convention; `deontic-norms` returns the
  SDL closure; `directive-status` reads task-state groups.
- `--skill-registry` mode: the installed `skills.metta` loads under PeTTa and
  `getSkills` renders the original catalogue plus the deontic and directive skills;
  idempotent re-run and byte-exact uninstall.
- Docker overlay: builds clean against `singularitynet/omegaclaw:latest`. The
  installer runs during the build (clone at `/PeTTa/repos/OmegaClaw-Core`, 31 files
  under `--minimal`, both patches applied) and the image exports as
  `omegaclaw-deontic:latest`.

## Known limitations

- Building the overlay needs an isolated `DOCKER_CONFIG` (an empty `{}`) where the
  box's Docker config references a credential helper that is absent from PATH; the
  public base image then pulls anonymously. The overlay itself builds and installs
  correctly.
- Semantic retrieval needs the `faiss_ffi` native build, hence the gate.
- The installer edits two core files in place. A load-time plugin seam would avoid
  that, at the cost of an upstream change; this bundle keeps to a frozen upstream.
