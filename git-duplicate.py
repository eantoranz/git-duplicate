#!/usr/bin/python3

"""
Copyright (c) 2022-2024 Edmundo Carmona Antoranz
Released under the terms of GPLv2

This script can be used in cases when we want to _duplicate_
commits on top of another branch that has the same tree
when the commits we want to duplicate are **not** linear.
Look at this example from git project itself:

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
 - allow complete disconnection from original tree
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
parser.add_argument("--isolate", action="store_true", default=False,
		    help="Only consider commits that will be duplicated as parents.")
parser.add_argument("--verify", action="store_true", default=False,
		    help="Verify that every commit actually matches what is expected (trees and parents match between original and duplicate commit)")
parser.add_argument('old_base', metavar="old-base", type=str,
		    help="Old base of commits to duplicate from. "
			"This commit has the same tree as the new_base")
parser.add_argument('tip', metavar="tip", type=str,
		    help="Tip of commits to duplicate.")
args = parser.parse_args()

import os
import subprocess
import sys

# list of commits to be duplicated
GIT_COMMITS: list[str] | None = None
TOTAL_COMMITS = 0 # total of commits that will be duplicated
# map old commit ids -> new commit ids
COMMITS_MAP: dict[str, str]=dict()
OLD_ROOT_COMMIT: str | None = None
NEW_ROOT_COMMIT: str | None = None

VERBOSE = args.verbose
VERIFY = args.verify
ISOLATE = args.isolate
PROGRESS: bool | None = None


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
		return git_rev_parse(commit + "^{tree}")
	except:
		raise Exception(f"Could not find tree oid for commit {commit}")

def git_get_parents(commit: str) -> list[str]:
	parents=[]
	n=1
	while True:
		try:
			parent = git_rev_parse(f"{commit}^{n}")
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
	exitcode, stdout, stderr = git_run(["show", "--quiet", f"--pretty='{value}'", commit])
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
	arguments.append(commit + "^{tree}")
	output = subprocess.check_output(arguments, stdin=ps.stdout)
	return remove_eol(output.decode())

def verify_commit(old_commit: str, new_commit: str) -> None:
	"""
	Make sure that the new commit matches what is expected from it.
	
	- trees are the same between old and new commit
	- parents match (there might be links to parents that are not to be processed)
	
	more things could be checked for thoroughness' sake (author info, message, etc)
	but won't consider that for the time being
	"""
	global OLD_ROOT_COMMIT, NEW_ROOT_COMMIT, GIT_COMMITS, COMMITS_MAP, ISOLATE

	error = False

	old_tree = git_get_tree(old_commit)
	old_parents = git_get_parents(old_commit)
	new_tree = git_get_tree(new_commit)
	new_parents = git_get_parents(new_commit)

	# trees
	if old_tree != new_tree:
		sys.stderr.write(f"BUG: trees do not match between old commit ({old_commit}) and new commit ({new_commit}):\n")
		sys.stderr.write(f"New commit's tree should be {old_tree} as in the old commit but got {new_tree} instead.\n")
		sys.stderr.write("\n")
		error = True

	# number of parents
	if not ISOLATE and len(old_parents) != len(new_parents):
		sys.stderr.write(f"BUG: Number of parents is not the same between old commit ({old_commit}) and new commit ({new_commit}):\n")
		sys.stderr.write(f"New commit has {len(old_parents)} parents: {old_parents}.\n")
		sys.stderr.write(f"Old commit has {len(new_parents)} parents: {new_parents}.\n")
		sys.stderr.write("\n")
		error = True
	elif len(old_parents) < len(new_parents):
		sys.stderr.write(f"BUG: Number of parents of the old commit ({old_commit}) is smaller than the parents of the new commit ({new_commit}):\n")
		sys.stderr.write(f"New commit has {len(old_parents)} parents: {old_parents}.\n")
		sys.stderr.write(f"Old commit has {len(new_parents)} parents: {new_parents}.\n")
		sys.stderr.write("\n")
		error = True
	else:
		# do the parents match each other?
		i = 0 # index for old parents
		j = 0 # index for new parents
		while i < len(old_parents):
			old_parent = old_parents[i]
			if j >= len(new_parents):
				if old_parent in GIT_COMMITS:
					sys.stderr.write(f"BUG: inconsistency detected for new commit {new_commit}:\n")
					sys.stderr.write(f"Old commit {old_commit} has {old_parent} as a parent.\n")
					sys.stderr.write(f"This old commit parent is in the list of commits to be duplicated and so it has to be included as a parent of the new commit.\n")
					sys.stderr.write(f"Unfortunately that is not the case.\n")
					sys.stderr.write("\n")
					error = True
				i += 1
				continue

			new_parent = new_parents[j]
			if old_parent in GIT_COMMITS:
				# there has to be a mapping to this commit and it has to match the new parent
				if (mapped_parent := COMMITS_MAP.get(old_parent)) != new_parent:
					if old_parent == OLD_ROOT_COMMIT:
						if new_parent != NEW_ROOT_COMMIT:
							sys.stderr.write(f"BUG: inconsistency detected for a parent of new commit {new_commit}:\n")
							sys.stderr.write(f"Old commit {old_commit} has {old_parent} as a parent.\n")
							sys.stderr.write(f"This old commit has to be mapped to the root commit of the duplication process ({NEW_ROOT_COMMIT}).\n")
							sys.stderr.write(f"This parent in the new duplicated commit does not match this value: {new_parent}.\n")
							sys.stderr.write("\n")
							error = True

				# trees have to match between the parents
				old_parent_tree = git_get_tree(old_parent)
				new_parent_tree = git_get_tree(new_parent)
				
				if old_parent_tree != new_parent_tree:
					sys.stderr.write(f"BUG: inconsistency detected for a parent of new commit {new_commit}:\n")
					sys.stderr.write(f"Old commit {old_commit} has {old_parent} as a parent and this parent has tree {old_parent_tree}.\n")
					sys.stderr.write(f"New commit {new_commit} has {new_parent} as a parent and this parent has tree {new_parent_tree}.\n")
					sys.stderr.write(f"The trees must be the same. Looks like the script messed up choosing this (new) parent while duplicating commit {old_commit}.\n")
					sys.stderr.write("\n")
					error = True

				# we can check the next new parent
				j += 1
			elif not ISOLATE:
				if  old_parent != new_parent:
					sys.stderr.write(f"BUG: inconsistency detected for a parent of new commit {new_commit}:\n")
					sys.stderr.write(f"Parent {old_parent} from old commit {old_commit} is not to be duplicated so it has to be included as a direct parent of the new commit.\n")
					sys.stderr.write(f"We are finding commit {new_parent} as a parent instead.\n")
					sys.stderr.write(f"Looks like the script messed up not choosing the old commit's parent as a parent of the new commit while duplicating commit {old_commit}.\n")
					sys.stderr.write("\n")
					error = True
				else:
					# a parent that is outside of the commits to be duplicated
					# and we are linking missing parents
					j += 1
			else:
				if old_parents in new_parents:
					sys.stderr.write(f"BUG: inconsistency detected for a parent of new commit {new_commit}:\n")
					sys.stderr.write(f"Parent {old_parent} from old commit {old_commit} is not to be duplicated and it is not to be included as a parent of the new commit.\n")
					sys.stderr.write(f"We are finding it as a parent of new commit {new_commit}. Parents: {new_parents}.\n")
					sys.stderr.write(f"Looks like the script messed up choosing the old commit's parent as a parent of the new commit while duplicating commit {old_commit}.\n")
					sys.stderr.write("\n")
					error = True

			# go to next old parent
			i += 1


	if error:
		sys.stderr.write("Please, report this to git-duplicate's maintainer if possible.\n")
		sys.stderr.flush()
		raise Exception(f"There are inconsistencies between old commit {old_commit} and {new_commit}. Check stderr output for information.")

def duplicate(commit: str, commit_count: int) -> (str, int):
	"""
	Duplicate a commit
	
	Return the new oid of the commit
	"""
	global COMMITS_MAP
	global TOTAL_COMMITS
	global ISOLATE
	global VERBOSE
	global PROGRESS
	global VERIFY

	if new_commit := COMMITS_MAP[commit]:
		if new_commit != "pending":
			# already duplicated
			return new_commit, commit_count

	# get parents for said commit
	orig_parents = git_get_parents(commit)
	# get the mapped commits for each parent
	new_parents = []
	for orig_parent in orig_parents:
		if new_parent := COMMITS_MAP.get(orig_parent):
			# the commit has to be duplicated
			if new_parent == "pending":
				# the commit is _pending_ to be duplicated
				new_parent, commit_count = duplicate(orig_parent, commit_count) # got the new id
				COMMITS_MAP[orig_parent] = new_parent
		elif not ISOLATE:
			# have to use the original parent commit in the new commit
			new_parent = orig_parent
		else:
			# this parent is not in the list of commits to be duplicated so skipping it
			continue
		new_parents.append(new_parent)

	# now we need to create the new commit
	new_commit = git_duplicate_commit(commit, new_parents)
	COMMITS_MAP[commit] = new_commit
	commit_count += 1

	if VERIFY:
		verify_commit(commit, new_commit)

	if PROGRESS:
		sys.stdout.write(f"\rDuplicating commits... ({commit_count}/{TOTAL_COMMITS})\r")
		sys.stdout.flush()
	
	if VERBOSE:
		sys.stderr.write(f"{commit} -> {new_commit}\n")
		sys.stderr.flush()
	
	return new_commit, commit_count


## main program starts here

OLD_ROOT_COMMIT = git_rev_parse(args.old_base)
NEW_ROOT_COMMIT = git_rev_parse(args.onto)

if args.progress:
	PROGRESS = True
elif args.no_progress:
	PROGRESS = False
else:
	PROGRESS=sys.stdout.isatty()

# let's compare the trees of the old-tip and the new-tip

onto_tree=git_get_tree(args.onto)
old_base_tree=git_get_tree(args.old_base)

if (onto_tree != old_base_tree):
	sys.stderr.write(f"New base tree from {args.onto}: {onto_tree}\n")
	sys.stderr.write(f"Old base tree from {args.old_base}: {old_base_tree}\n")
	sys.stderr.flush()
	raise Exception("The trees of the two base commits is not the same")

# let's get the list of commits that will need to be duplicated
exit_code, raw_git_commits, error = git_run(["rev-list", f"{args.old_base}..{args.tip}"])
if exit_code != 0:
	sys.stderr.write(error)
	sys.stderr.flush()
	raise Exception("There was an error getting commits to be duplicated")
GIT_COMMITS = list(commit_id for commit_id in raw_git_commits.split("\n") if len(commit_id) > 0)
TOTAL_COMMITS = len(GIT_COMMITS)

for commit in GIT_COMMITS:
	COMMITS_MAP[commit] = "pending" # a value that we will never see as a commit id

# need to insert a mapping between the old base and the new base
COMMITS_MAP[OLD_ROOT_COMMIT] = NEW_ROOT_COMMIT

commit_count = 0
for orig_commit in reversed(GIT_COMMITS):
	_, commit_count = duplicate(orig_commit, commit_count)
if PROGRESS:
	print()
print(COMMITS_MAP[GIT_COMMITS[0]])
