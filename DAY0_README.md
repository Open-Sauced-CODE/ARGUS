# Phase 6 Day-0 pack (Shaurya commits this to main FIRST; Prabhav branches after)

Copy the files in this pack into the repo root (they are already laid out by path), then:

    git checkout main && git pull
    # 1) append the two snippets
    type DAY0_APPEND_TO_GITATTRIBUTES.txt >> .gitattributes        (PowerShell: Get-Content ... | Add-Content .gitattributes)
    type DAY0_APPEND_TO_GITIGNORE.txt     >> .gitignore
    # 2) prove the guard works, then commit
    python tools/check_ownership.py --who shaurya --base origin/main
    git add ml/train_m2 ml/README_contracts_phase6.md tools .gitattributes .gitignore
    git commit -m "phase6(shared): ownership map, harvest contract, input list, guard script"
    git push origin main
    # 3) tell Prabhav: "Day-0 is on main, branch from it"

The pack does NOT include the harvester, validator, labeler or any model code. Those are the two tracks' work.

NOTE: if `ml/train_m2/README.md` is still the one-line placeholder, leave it alone (shared file, no change needed).
If `ml/train_m2/__init__.py` or `ml/README_contracts_phase6.md` already exist in the repo, keep the repo's version and skip the pack's copy.
