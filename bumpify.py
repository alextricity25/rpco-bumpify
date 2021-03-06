#!/usr/bin/env python

import argparse
import os
import github3
import sh
import shutil
import subprocess

# This script will create a github issue on RPCO to bump the SHA,
# make the sha bump locally, make a commit, push a branch to RPCO,
# then make a pull request on RPCO.

def _cleanup(working_dir):
    shutil.rmtree(working_dir, ignore_errors=True)

def build_args():
    parser = argparse.ArgumentParser(
        description="Make a OSA SHA bump on RPCO for any given branch!")
    parser.add_argument(
        '--owner',
        '-o',
        default='rcbops',
        required=False,
        help="The owner of the rpc-openstack repo"
    )
    parser.add_argument(
        '--user',
        '-u',
        default='alextricity25',
        required=False,
        help='The github user name to use'
    )
    parser.add_argument(
        '--github_token',
        '-t',
        required=True,
        help="Your github token"
    )
    parser.add_argument(
        '--osa_branch',
        '-b',
        required=True,
        help='The branch in which the OSA SHA will be updated'
    )
    parser.add_argument(
        '--rpco_branch',
        '-r',
        required=True,
        help='The RPCO branch whose OSA SHA will be bumped.'
    )
    parser.add_argument(
        '--smoke',
        '-s',
        required=False,
        action='store_true',
        help='smoke run'
    )

    return parser

def main():

    # Variables
    labels = [
        "prio-expedited",
        "swimlane-enhancements",
        "status-needs-review-ready"
    ]

    parser = build_args()
    args = parser.parse_args()
    rpco_github_repo_url = "git@github.com:{}/rpc-openstack.git".format(
        args.owner
    )
    working_dir = "/tmp/bumpify/"
    git = sh.git.bake(_cwd=working_dir)

    # Create working directory. This directory will be cleaned up
    # after program execution.
    if not os.path.exists(working_dir):
        os.makedirs(working_dir)


    # Make a github issue on rpc-openstack to track the SHA bump
    gh = github3.GitHub(token=args.github_token)
    gh_repo = gh.repository(args.owner, 'rpc-openstack')
    issue_title = "[{}] - Update OSA SHA".format(args.rpco_branch)
    issue_body = (
        "It's that time again!"
    )

    print "---Creating github issue on {}/rpc-openstack...".format(args.owner)
    if not args.smoke:
        issue = gh_repo.create_issue(title=issue_title,
                                     body=issue_body,
                                     labels=labels)
    print "---Issue created!"

    if not args.smoke:
        branch_name = "cantu/issue/{}/{}".format(
            issue.number,
            args.rpco_branch
        )
    else:
        branch_name = "cantu/testing/bumpify"

    # Clone the rpc-openstack repository from github
    rpc_working_dir = "{}/rpc-openstack".format(working_dir)
    osa_working_dir = "{}/openstack-ansible".format(rpc_working_dir)
    print "---Cloning the RPCO repo!"
    try:
        git.clone("--recursive", rpco_github_repo_url)
        # Checkout the RPCO branch we are bumping the SHA for
        print "---Checking out {}".format(args.rpco_branch)
        git.checkout(
            args.rpco_branch,
            _cwd=rpc_working_dir
        )

        print "---Updating submodule"
        git.submodule.update(_cwd=rpc_working_dir)

        # Get the SHA of the current OSA
        #git_describe_output = git.describe(_cwd=osa_working_dir)
#        git_log_output = git.log('--format=format:%H','-1', _cwd=osa_working_dir)
#        if args.smoke:
#            print "Current OSA SHA:"
#            print git_log_output
#        current_sha = str(git_log_output.stdout)

        git_log_command = ['git', 'log', '--format=format:%H', '-1']
        git_log_command_p = subprocess.Popen(git_log_command,
                                             cwd=osa_working_dir,
                                             stdout=subprocess.PIPE)
        current_sha = git_log_command_p.communicate()[0]
        if args.smoke:
            print "Current OSA SHA: {}".format(current_sha)

        # Checkout the OSA branch with the commit we want to bump to
        print "---Making a new branch for the SHA bump"
        git.checkout(
            b=branch_name,
            _cwd=rpc_working_dir
        )

        print "---Getting the OSA branch we want the SHA of"
        git.checkout("origin/{}".format(args.osa_branch),
                    _cwd=osa_working_dir)

        git_log_command = ['git', 'log', '--format=format:%H', '-1']
        git_log_command_p = subprocess.Popen(git_log_command,
                                             cwd=osa_working_dir,
                                             stdout=subprocess.PIPE)
        new_sha = git_log_command_p.communicate()[0]
        if args.smoke:
            print "New OSA SHA: {}".format(new_sha)

        print "---Generating OSA diff"
        # Generate osa-differ and covert to GitHub markdown
        osa_differ_command = ['osa-differ',
                              current_sha,
                              new_sha,
                              '-u',
                              '--skip-projects',
                              '--release-notes']
        if args.smoke:
            print "osa-differ command:"
            print osa_differ_command
        osa_differ_p = subprocess.Popen(osa_differ_command, stdout=subprocess.PIPE)
        osa_differ_p.wait()
        pandoc_command = ['pandoc', '--from', 'rst', '--to', 'markdown_github']
        pandoc_command_p = subprocess.Popen(pandoc_command, stdin=osa_differ_p.stdout,
                                            stdout=subprocess.PIPE)
        osa_differ_p.stdout.close()
        differ_output = pandoc_command_p.communicate()[0]
        if args.smoke:
            print differ_output

        if pandoc_command_p.returncode:
            print "osa-differ has failed to run"
            exit()

        # Committing the SHA bump
        git.add(
            "openstack-ansible",
            _cwd=rpc_working_dir
        )
        print "---Making the commit"
        if not args.smoke:
            git.commit(
                m="{}\n\n{}".format(
                    "[{}] Update OSA SHA".format(args.rpco_branch),
                    "Connects https://github.com/{}/rpc-openstack/issues/{}".format(
                        args.owner,
                        issue.number
                    )
                ),
                _cwd=rpc_working_dir
            )
        print "---Pushing the branch up"
        if not args.smoke:
            git.push(
                "origin",
                branch_name,
                _cwd=rpc_working_dir
            )
        # Create pull request
        print "---Creating pull request"
        if not args.smoke:
            gh_repo.create_pull(title="[{}] Update OSA SHA".format(args.rpco_branch),
                                body="{}\nConnects https://github.com/{}/rpc-openstack/issues/{}".format(
                                    differ_output,
                                    args.owner,
                                    issue.number
                                    ),
                                base=args.rpco_branch,
                                head=branch_name
                                )
        print "---Cleaning up"
        _cleanup(working_dir)
    except Exception as e:
        print str(e)
        print "There was an error. Cleaning up."
        _cleanup(working_dir)
        exit()

if __name__ == "__main__":
    main()
