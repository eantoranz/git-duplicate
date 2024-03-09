#!/usr/bin/python3

"""
Copyright (c) 2022-2024 Edmundo Carmona Antoranz
Released under the terms of GPLv2

This script can be used in cases when we want to _duplicate_
revisions on top of another branch that has the same tree
when the revisions we want to duplicate are **not** linear.
Look at this example:
$ git checkout v2.35.0
# create a revision that has the exact same tree as v2.35.0
$ git commit --amend --no-edit
# Replay all revisions between v2.35.0 and v2.36-rc0
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
Rebase is using the merge engine to duplicate all the revisions, for understandable reasons.
`git-duplicate.py` would instead recreate all the original revisions on top of HEAD without
running any actual merge.
Technically speaking, the script will create new revisions using the same metadata from the
original revisions, except that it would change the parent IDs and the committer.

When you use this script, it won't move anything from the local repo, it will only
create commits as requested and, when it is finished, it will write the commit ID of the
tip of the resulting rebased/dupolicated branch, much the same way git-commit-tree behaves.

$ ./git-duplicate.py HEAD v2.35.0 v2.36.0-rc0
It might not look like it but...
I am working. Check CPU and disk usage.
f0b7663aa1b6e009e27c185b89ad88f683d773aa

TODO
 - careful with tags
"""

import argparse

parser=argparse.ArgumentParser(
	description=
		'Duplicate revisions on top of other revisions.\n'
		'\n'
		'Think of it as running:\n'
		'git rebase --rebase-merges old-base tip --onto new-base\n'
		'\n'
		'When it finishes running, it will print the commit ID\n'
		'of the tip of the rebased/duplicated branch',
	formatter_class=argparse.RawTextHelpFormatter
)

parser.add_argument("--keep-committer", action='store_true',
		     help="Keep the original committer from the revision")
parser.add_argument('new_base', metavar='new-base', type=str,
                    help='New base of revisions to work on')
parser.add_argument('old_base', metavar="old-base", type=str,
		    help="Old base of revisions to duplicate from. "
			"This revision has the same tree as the new_base")
parser.add_argument('tip', metavar="tip", type=str,
		    help="Tip of revisions to duplicate.")
parser.add_argument('--verbose', action='store_true',
		    help="Show the equivalent commits.")
parser.add_argument("--progress", action="store_true", default=False,
		    help="Enforce showing progress. Progress will be shown by default if working on a terminal.")
parser.add_argument("--no-progress", action="store_true", default=False,
		    help="Avoid showing progress")
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

def git_get_tree(revision: str) -> str:
	"""
	Given a revision, get its tree oid
	"""
	try:
		return git_rev_parse("%s^{tree}" % revision)
	except:
		raise Exception("Could not find tree oid for revision %s" % revision)

def git_get_parents(revision: str) -> list[str]:
	parents=[]
	n=1
	while True:
		try:
			parent = git_rev_parse("%s^%d" % (revision, n))
			parents.append(parent)
		except:
			# no more parents
			break
		n+=1
	return parents

def git_get_revision_value(revision: str, value: str) -> str:
	"""
	Get a value from a revision, using pretty format from log
	"""
	exitcode, stdout, stderr = git_run(["show", "--quiet", "--pretty='%s'" % value, revision])
	if exitcode != 0:
		raise Exception(f"Error getting value from revision {revision}: {stderr}")
	return remove_eol(stdout) # ony the last eol is removed, in case it is multiline

def git_load_revision_information(revision: str) -> None:
	"""
	Load revision information as environment variables
	"""
	global args
	os.environ["GIT_AUTHOR_NAME"] = git_get_revision_value(revision, '%an')
	os.environ["GIT_AUTHOR_EMAIL"] = git_get_revision_value(revision, '%ae')
	os.environ["GIT_AUTHOR_DATE"] = git_get_revision_value(revision, '%aD')
	
	# TODO the committer might be optionally kept from the revision
	if args.keep_committer:
		os.environ["GIT_COMMITTER_NAME"] = git_get_revision_value(revision, '%cn')
		os.environ["GIT_COMMITTER_EMAIL"] = git_get_revision_value(revision, '%ce')
		os.environ["GIT_COMMITTER_DATE"] = git_get_revision_value(revision, '%cD')

def git_duplicate_revision(revision, parents):
	git_load_revision_information(revision)
	ps = subprocess.Popen(("git", "show", "--quiet", "--pretty=%B", revision), stdout=subprocess.PIPE)
	arguments = ["git", "commit-tree"]
	for parent in parents:
		arguments.extend(["-p", parent])
	arguments.append("%s^{tree}" % revision)
	output = subprocess.check_output(arguments, stdin=ps.stdout)
	return remove_eol(output.decode())

# let's compare the trees of the old-tip and the new-tip

new_base_tree=git_get_tree(args.new_base)
old_base_tree=git_get_tree(args.old_base)

if (new_base_tree != old_base_tree):
	sys.stderr.write("New base tree: %s\n" % new_base_tree)
	sys.stderr.write("Old base tree: %s\n" % old_base_tree)
	sys.stderr.flush()
	raise Exception("The trees of the two base revisions is not the same")

# let's get the list of revisions that will need to be duplicated
exit_code, git_revisions, error = git_run(["rev-list", f"{args.old_base}..{args.tip}"])
if exit_code != 0:
	sys.stderr.write(error)
	sys.stderr.flush()
	raise Exception("There was an error getting revisions to be duplicated")
git_revisions=git_revisions.split("\n")

revisions=dict()
for revision in git_revisions:
	if len(revision) == 0:
		# end of list
		continue
	revisions[revision] = None

# need to insert a mapping between the old base and the new base
revisions[git_rev_parse(args.old_base)] = git_rev_parse(args.new_base)

def duplicate(revision: str, revision_count: int, total_revisions: int) -> (str, int):
	"""
	Duplicate a revision
	
	Return the new oid of the revision
	"""
	global revisions, args, PROGRESS
	# get parents for said revision
	orig_parents = git_get_parents(revision)
	# get the mapped revisions for each parent
	parents=[]
	for parent in orig_parents:
		if parent in revisions:
			# the revision had to be duplicated
			if revisions[parent] is None:
				# the revision is _pending_ to be duplicated
				new_parent, revision_count = duplicate(parent, revision_count, total_revisions) # got the new id
				revisions[parent] = new_parent
			parents.append(revisions[parent])
		else:
			# have to use the original parent revision
			parents.append(parent)
	
	# now we need to create the new revision
	new_revision = git_duplicate_revision(revision, parents)

	revision_count += 1
	if PROGRESS:
		sys.stdout.write(f"\rDuplicating revisions ({revision_count}/{total_revisions})")
		sys.stdout.flush()
	
	if (args.verbose):
		sys.stderr.write(f"{revision} -> {new_revision}\n")
		sys.stderr.flush()
	
	return new_revision, revision_count

total_revisions = len(git_revisions) - 1 # there is a mapping between the bases
new_revision, revisions_count = duplicate(git_revisions[0], 0, total_revisions)
if PROGRESS:
	print()
print(new_revision)
