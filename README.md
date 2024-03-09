# usage

This script can be used in cases when we want to _duplicate_
revisions on top of another branch that has the same tree
when the revisions we want to duplicate are not linear.
Look at this example:

```
$ git checkout v2.35.0
# create a revision that has the exact same tree as v2.35.0
$ git commit --amend --no-edit
# Duplicate all revisions between v2.35.0 and v2.36-rc0
$ git rebase --onto HEAD v2.35.0 v2.36.0-rc0 --rebase-merges
.
.
.
Could not apply 5d01301f2b... Sync-with-Git-2-35-1 # Sync with Git 2.35.1
$ git status
interactive rebase in progress; onto 9c7bc0e364
Last commands done (247 commands done):
   pick 90fb70e458 Name the next one 2.36 to prepare for 2.35.1
   merge -C 5d01301f2b865aa8dba1654d3f447ce9d21db0b5 Sync-with-Git-2-35-1 # Sync with Git 2.35.1
  (see more in file /home/antoranz/proyectos/git/git/.git/worktrees/master/rebase-merge/done)
Next commands to do (982 remaining commands):
   label branch-point
   pick 5e00514745 t1405: explictly delete reflogs for reftable
  (use "git rebase --edit-todo" to view and edit)
You have unmerged paths.
  (fix conflicts and run "git commit")
  (use "git merge --abort" to abort the merge)
Changes to be committed:
        new file:   Documentation/RelNotes/2.35.1.txt
Unmerged paths:
  (use "git add <file>..." to mark resolution)
        both modified:   GIT-VERSION-GEN
        both modified:   RelNotes
```

Rebase is using the merge engine to duplicate all the revisions, for understandable reasons.
`git-duplicate.py` would instead recreate all the original revisions on top of the desired
point (doesn't have to be `HEAD`) without running any actual merge.

Technically speaking, the script will create new revisions using the same metadata from the
original revisions, except that it would change the parent IDs and the committer.

When you use this script, it won't move any reference in the local repo, it will only
create commits as requested and, when it is finished, it will write the commit ID of the
tip of the resulting rebased/duplicated branch, much the same way git-commit-tree behaves.

By default, it assumes you mean to rebase on top of `HEAD`. If that is not the case, use
`--onto` to specify what should be the new base for the rebase.

```
$ ./git-duplicate.py v2.35.0 v2.36.0-rc0
Duplicating revisions (852/852)
b05eb5765b3debfa6937b141c835b9eb9c098bf5
```

# copyright/license

Copyright (c) 2022-2024 Edmundo Carmona Antoranz

Released under the terms of GPLv2
