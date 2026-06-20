; Agent-facing deontic skills (Feature B1, opt-in).
;
; Thin wrappers exposing lib_deontic through the skill dispatcher, so the agent
; can consult the defeasible/deontic engine during its loop — e.g. as a guardrail
; that checks whether a planned action complies with the loaded norms before it
; acts, or to resolve which of several conflicting rules should win.
!(import! &self (library OmegaClaw-Core lib_deontic))

; Defeasible conclusions of a theory file (tagged +D/-D definite, +d/-d defeasible).
(= (deontic-conclude $path) (dl-run $path))

; Conclusions under the Standard Deontic Logic closure (O/P/F interact; F p = O not p).
(= (deontic-norms $path) (dl-run-deontic $path))

; Unresolved deontic dilemmas: O p and O not-p both applicable, neither resolved.
(= (deontic-conflicts $path) (deontic-dilemmas $path))

; Catalog lines advertising the skills to the LLM (spliced into getSkills).
(= (deontic-skills-doc)
   ("- Defeasible + deontic reasoning over a theory file: deontic-conclude path"
    "- Conclusions under Standard Deontic Logic closure: deontic-norms path"
    "- Detect unresolved deontic dilemmas (O p and O not p both applicable): deontic-conflicts path"))
