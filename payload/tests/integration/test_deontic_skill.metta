; Feature B1: agent-facing deontic skill wrappers over lib_deontic.
!(import! &self (library OmegaClaw-Core src/skills_deontic))

; deontic-conclude returns the tagged conclusion set
!(test (is-member (pd (lit pos none none penguin ()))
                  (deontic-conclude (dl-path examples/deontic/penguin.metta))) True)

; deontic-conflicts surfaces an unresolved O p / O not-p dilemma
!(test (size-atom (deontic-conflicts (dl-path examples/deontic/deontic_dilemma.metta))) 1)
; ...and reports none on a theory with no competing obligations
!(test (size-atom (deontic-conflicts (dl-path examples/deontic/penguin.metta))) 0)

; the catalog advertises three skills to the LLM
!(test (size-atom (deontic-skills-doc)) 3)

!(println! test-deontic-skill-done)
