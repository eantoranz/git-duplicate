# rebase--

`git-duplicate` works under the condition that the original _"base commit"_
and the _"onto commit"_ have the same _"tree"_. Because of that, it can be safely
asserted that all resulting rebased commits would have the same tree as the original
commits so no need to run the merges (and the reason why `git-duplicate` works so
fast): Just create new commits with new metadata using the original trees, no need
to run **any** merging operations at all and no need to move the working tree around
while the rebase operation is taking place.

This, of course, makes the usability of `git-duplicate` **too narrow** as
there are very few rebasing scenarios where the premise about the base commits
having the same trees holds water.

Hence, it is mandatory to find ways to leverage original commits
even if the _bases_ are not the same.

I have started a tool that does just that:
[rebase--](https://github.com/eantoranz/rebase--).

If you are working on a rebase scenario where the 2 bases do not have the
same tree (almost every rebase scenario out there, for all practical purposes),
**please**, give it a try.

`rebase--` by default, just like `git-duplicate`, will not change your
working tree state. It will only report the final commit id for the rebase
you requested if the rebase is sucessful.

# usage

This script can be used in cases when we want to _duplicate_
commits on top of another branch that has the same tree
when the commits we want to duplicate are not linear.
Look at this example using tags from [git project](https://github.com/git/git)
itself:

```
$ git checkout v2.35.0
# create a commit that has the exact same tree as v2.35.0
$ git commit --amend --no-edit
# Duplicate all commits between v2.35.0 and v2.36-rc0
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

Rebase is using the merge engine to duplicate all the commits, for understandable reasons.
`git-duplicate.py` would instead recreate all the original commits on top of the desired
point (doesn't have to be `HEAD`) without running any actual merge.

Technically speaking, the script will create new commits using the same metadata from the
original commits, except that it would change the parent IDs and the committer.

When you use this script, it won't move any reference in the local repo, it will only
create commits as requested and, when it is finished, it will write the commit ID of the
tip of the resulting rebased/duplicated branch, much the same way git-commit-tree behaves.

By default, it assumes you mean to rebase on top of `HEAD`. If that is not the case, use
`--onto` to specify what should be the new base for the rebase.

```
$ ./git-duplicate.py v2.35.0 v2.36.0-rc0
Duplicating commits (852/852)
b05eb5765b3debfa6937b141c835b9eb9c098bf5
```

# use cases

## Rewording a commit in a non-linear branch

When needing to amend a commit, what is usually done is an *interactive rebase*
choosing to reword a given commit. In linear branches, there's no much hassle.
Unfortunately, on **non-liear** branches `--rebase-merges` will need to be used
and, even though trees are exactly the same, git won't consider them and will
run a full merge operation on them. If there had been conflicts in the original
commits, facing those conflicts again will be unavoidable.

`git-duplicate.py` can help in this situacion as it will replicate
the original history on top of the new commit coming out of ament.

Suppose you are on branch `some-branch` and you want to reword commit `X`.

```
* aaae (some-branch)
|\
* \ aaad
|\ \
| * | aaac
| * | aaab
* | | aaaa
* | | aaa9
|/ /
* / aaa8
* | aaa7
* | aaa6 (X)
|\|
| * aaa5
| * aaa4
* | aaa3
* | aaa2
|/
* aaa1
* aaa0
```

Use the following sequence of commands:
```
git checkout X
git commit --amend -m "New message for the commit"
./git-duplicate X some-branch
```

Assuming the resulting commit is `bbb8`, that will create the
following history for that commit:
```
* bbb8
|\
* \ bbb7
|\ \
| * | bbb6
| * | bbb5
* | | bbb4
* | | bbb3
|/ /
* / bbb2
* | bbb1
* | bbb0 New message for the commit (HEAD)
|\|
| * aaa5
| * aaa4
* | aaa3
* | aaa2
|/
* aaa1
* aaa0
```

## squash a number of commits and then reapply all following commits

Suppose you start from the following chart:
```
* aaae (some-branch)
|\
* \ aaad
|\ \
| * | aaac
| * | aaab
* | | aaaa
* | | aaa9
|/ /
* / aaa8
* | aaa7
* | aaa6
|\|
| * aaa5
| * aaa4
* | aaa3
* | aaa2
|/
* aaa1
* aaa0
```

Let's squash the changes in `aaa6..aaa8` into a single commit, then reapply all changes
in `aaa8..aaae` on top of the resulting commit. Use the following recipe:

```
git checkout aaa6
git restore --source aaa8 --worktree --index -- .
git commit -m "A new commit to get changes in aaa6..aaa8"
./git-duplicate.sh aaa6 some-branch
```

Assuming the resulting commit is `bbb5`, the resulting history
for that commit would be:
```
* bbb5 (some-branch)
|\
* \ bbb4
|\ \
| * | aaac
| * | bbb3
* | | bbb2
* | | bbb1
|/ /
* / bbb0 "A new commit to get changes in aaa6..aaa8" (HEAD)
|\|
| * aaa5
| * aaa4
* | aaa3
* | aaa2
|/
* aaa1
* aaa0
```

## Start branch history from a given commit

In cases when you want to start your history of branch `some-brach` from commit `X` so that previous
commits do not show up in history:

```
* aaae (some-branch)
* aaab
|\
| * aaac
| * aaab
* | aaaa
* | aaa9
|/
* aaa8
* aaa7
* aaa6 (X)
|\
| * aaa5
| * aaa4
* | aaa3
* | aaa2
|/
* aaa1
* aaa0
```

This can be done like this:

```
git checkout --orphan new-branch X
git commit -m "Restarting history of the project"
./git-duplicate.py --isolate X some-branch
```

Assuming that the resulting commit id is `bbb8`, then the chart for that commit's history would be:

This will produce this chart:
```
* bbb8
* bbb7
|\
| * bbb6
| * bbb5
* | bbb4
* | bbb3
|/
* bbb2
* bbb1
* bbb0 (new-branch -> HEAD)
```

Using `--isolate` makes sure to avoid linking commits outside of the commits
that are being duplicated as parents.

# copyright/license

Copyright (c) 2022-2024 Edmundo Carmona Antoranz

Released under the terms of GPLv2
