#!/usr/bin/python3

"""
Copyright (c) 2022-2024 Edmundo Carmona Antoranz
Released under the terms of GPLv2

This script can be used in cases when we want to _duplicate_
commits on top of another branch that has the same tree
when the commits we want to duplicate are **not** linear.
Look at this example:
$ git checkout v2.35.0
# create a commit that has the exact same tree as v2.35.0
$ git commit --amend --no-edit
# Replay all commits between v2.35.0 and v2.36-rc0
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
End of example

Rebase is using the merge engine to duplicate all the commits, for understandable reasons.
`git-duplicate.py` would instead recreate all the original commits on top of HEAD without
running any actual merge.
Technically speaking, the script will create new commits using the same metadata from the
original commits, except that it would change the parent IDs and the committer.

Technically speaking, the script will create new commits using the same metadata from the
original commits, except that it would change the parent IDs and the committer.

When you use this script, it won't move any reference in the local repo, it will only
create commits as requested and, when it is finished, it will write the commit ID of the
tip of the resulting rebased/duplicated branch, much the same way git-commit-tree behaves.

By default, it assumes you mean to rebase on top of `HEAD`. If that is not the case, use
`--onto` to specify what should be the new base for the rebase.

$ ./git-duplicate.py v2.35.0 v2.36.0-rc0
Duplicating commits (852/852)
b05eb5765b3debfa6937b141c835b9eb9c098bf5

TODO
 - careful with tags
"""

import argparse

parser=argparse.ArgumentParser(
	description=
		'Duplicate commits on top of other commits.\n'
		'\n'
		'Think of it as running:\n'
		'git rebase --rebase-merges old-base tip --onto new-base\n'
		'\n'
		'When it finishes running, it will print the commit ID\n'
		'of the tip of the rebased/duplicated branch',
	formatter_class=argparse.RawTextHelpFormatter
)

parser.add_argument("--keep-committer", action='store_true',
		     help="Keep the original committer from the commit")
parser.add_argument('--verbose', action='store_true',
		    help="Show the equivalent commits.")
parser.add_argument("--progress", action="store_true", default=False,
		    help="Enforce showing progress. Progress will be shown by default if working on a terminal.")
parser.add_argument("--no-progress", action="store_true", default=False,
		    help="Avoid showing progress")
parser.add_argument("--onto", type=str,
		    help="On top of what commit should the rebase be performed? Default: HEAD", default="HEAD")
parser.add_argument('old_base', metavar="old-base", type=str,
		    help="Old base of commits to duplicate from. "
			"This commit has the same tree as the new_base")
parser.add_argument('tip', metavar="tip", type=str,
		    help="Tip of commits to duplicate.")
args = parser.parse_args()

import os
import subprocess
import sys

PROGRESS=None
if args.progress:
	PROGRESS=True
elif args.no_progress:
	PROGRESS=False
else:
	PROGRESS=sys.stdout.isatty()

def remove_eol(line: str) -> str:
	return line.rstrip("\n")

def git_run(arguments: [str]) -> tuple[str, int]:
	"""
	Run a git command, return it's output and exit code in a tuple
	"""
	git_args=["git"]
	git_args.extend(arguments)
	res = subprocess.run(git_args, capture_output=True)
	return (res.returncode, res.stdout.decode(), res.stderr.decode())

def git_rev_parse(revish: str) -> str:
	exitcode, stdout, stderr = git_run(["rev-parse", revish])
	if exitcode != 0:
		raise Exception(f"Could not run rev-parse of {revish}")
	return remove_eol(stdout)

def git_get_tree(commit: str) -> str:
	"""
	Given a commit, get its tree oid
	"""
	try:
		return git_rev_parse("%s^{tree}" % commit)
	except:
		raise Exception("Could not find tree oid for commit %s" % commit)

def git_get_parents(commit: str) -> list[str]:
	parents=[]
	n=1
	while True:
		try:
			parent = git_rev_parse("%s^%d" % (commit, n))
			parents.append(parent)
		except:
			# no more parents
			break
		n+=1
	return parents

def git_get_commit_value(commit: str, value: str) -> str:
	"""
	Get a value from a commit, using pretty format from log
	"""
	exitcode, stdout, stderr = git_run(["show", "--quiet", "--pretty='%s'" % value, commit])
	if exitcode != 0:
		raise Exception(f"Error getting value from commit {commit}: {stderr}")
	return remove_eol(stdout) # ony the last eol is removed, in case it is multiline

def git_load_commit_information(commit: str) -> None:
	"""
	Load commit information as environment variables
	"""
	global args
	os.environ["GIT_AUTHOR_NAME"] = git_get_commit_value(commit, '%an')
	os.environ["GIT_AUTHOR_EMAIL"] = git_get_commit_value(commit, '%ae')
	os.environ["GIT_AUTHOR_DATE"] = git_get_commit_value(commit, '%aD')
	
	# TODO the committer might be optionally kept from the commit
	if args.keep_committer:
		os.environ["GIT_COMMITTER_NAME"] = git_get_commit_value(commit, '%cn')
		os.environ["GIT_COMMITTER_EMAIL"] = git_get_commit_value(commit, '%ce')
		os.environ["GIT_COMMITTER_DATE"] = git_get_commit_value(commit, '%cD')

def git_duplicate_commit(commit, parents):
	git_load_commit_information(commit)
	ps = subprocess.Popen(("git", "show", "--quiet", "--pretty=%B", commit), stdout=subprocess.PIPE)
	arguments = ["git", "commit-tree"]
	for parent in parents:
		arguments.extend(["-p", parent])
	arguments.append("%s^{tree}" % commit)
	output = subprocess.check_output(arguments, stdin=ps.stdout)
	return remove_eol(output.decode())

# let's compare the trees of the old-tip and the new-tip

onto_tree=git_get_tree(args.onto)
old_base_tree=git_get_tree(args.old_base)

if (onto_tree != old_base_tree):
	sys.stderr.write(f"New base tree from {args.onto}: {onto_tree}\n")
	sys.stderr.write(f"Old base tree from {args.old_base}: {old_base_tree}\n")
	sys.stderr.flush()
	raise Exception("The trees of the two base commits is not the same")

# let's get the list of commits that will need to be duplicated
exit_code, git_commits, error = git_run(["rev-list", f"{args.old_base}..{args.tip}"])
if exit_code != 0:
	sys.stderr.write(error)
	sys.stderr.flush()
	raise Exception("There was an error getting commits to be duplicated")
git_commits=git_commits.split("\n")

commits=dict()
for commit in git_commits:
	if len(commit) == 0:
		# end of list
		continue
	commits[commit] = None

# need to insert a mapping between the old base and the new base
commits[git_rev_parse(args.old_base)] = git_rev_parse(args.onto)

def duplicate(commit: str, commit_count: int, total_commits: int) -> (str, int):
	"""
	Duplicate a commit
	
	Return the new oid of the commit
	"""
	global commits, args, PROGRESS
	# get parents for said commit
	orig_parents = git_get_parents(commit)
	# get the mapped commits for each parent
	parents=[]
	for parent in orig_parents:
		if parent in commits:
			# the commit had to be duplicated
			if commits[parent] is None:
				# the commit is _pending_ to be duplicated
				new_parent, commit_count = duplicate(parent, commit_count, total_commits) # got the new id
				commits[parent] = new_parent
			parents.append(commits[parent])
		else:
			# have to use the original parent commit
			parents.append(parent)
	
	# now we need to create the new commit
	new_commit = git_duplicate_commit(commit, parents)

	commit_count += 1
	if PROGRESS:
		sys.stdout.write(f"\rDuplicating commits ({commit_count}/{total_commits})")
		sys.stdout.flush()
	
	if (args.verbose):
		sys.stderr.write(f"{commit} -> {new_commit}\n")
		sys.stderr.flush()
	
	return new_commit, commit_count

total_commits = len(git_commits) - 1 # there is a mapping between the bases
new_commit, commits_count = duplicate(git_commits[0], 0, total_commits)
if PROGRESS:
	print()
print(new_commit)
