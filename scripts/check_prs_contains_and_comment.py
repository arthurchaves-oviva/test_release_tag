#!/usr/bin/env python3

import argparse
import os
import sys
from typing import Optional

try:
    from github import Github
    from github.Repository import Repository
    from github.PullRequest import PullRequest
except Exception as import_error:
    print("ERROR: Missing dependency 'PyGithub'. Install with: pip install PyGithub", file=sys.stderr)
    raise


def read_token_from_environment() -> Optional[str]:
    candidate_env_vars = [
        "GITHUB_TOKEN",
        "GH_TOKEN",
        "GITHUB_PAT",
        "TOKEN",
    ]
    for env_var in candidate_env_vars:
        token = os.environ.get(env_var)
        if token:
            return token
    return None


def get_github_client(explicit_token: Optional[str]) -> Github:
    token = explicit_token or read_token_from_environment()
    if not token:
        print(
            "ERROR: No GitHub token provided. Set GITHUB_TOKEN (or GH_TOKEN) or pass --token.",
            file=sys.stderr,
        )
        sys.exit(2)
    return Github(login_or_token=token)


def contains_all_pr_commits(repo: Repository, target_branch: str, pr: PullRequest) -> bool:
    """
    Returns True if the target_branch already contains all commits from the PR.

    Implementation detail: Uses the compare API base=target_branch ... head=PR head SHA.
    If status is 'behind' or 'identical', then base contains head's commits (or is equal).
    """
    comparison = repo.compare(base=target_branch, head=pr.head.sha)
    return comparison.status in ("behind", "identical")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "For each open PR in a repository, check whether a given branch already "
            "contains all commits from that PR. If yes, comment the provided status on the PR."
        )
    )
    parser.add_argument(
        "repo",
        help="Repository in the format 'owner/repo_name'",
    )
    parser.add_argument(
        "branch",
        help="Target branch name to check (e.g., 'release/qa')",
    )
    parser.add_argument(
        "status",
        help="Status text to post as a comment when the PR commits are contained",
    )
    parser.add_argument(
        "--state",
        choices=["open", "closed", "all"],
        default="open",
        help="Which PRs to process (default: open)",
    )
    parser.add_argument(
        "--token",
        help="GitHub token (overrides GITHUB_TOKEN/ GH_TOKEN env vars)",
    )

    args = parser.parse_args()

    gh = get_github_client(args.token)
    try:
        repo: Repository = gh.get_repo(args.repo)
    except Exception as fetch_repo_error:
        print(f"ERROR: Could not access repo '{args.repo}': {fetch_repo_error}", file=sys.stderr)
        sys.exit(2)

    print(f"Repository: {args.repo}")
    print(f"Target branch: {args.branch}")
    print(f"PR state: {args.state}")

    pulls = repo.get_pulls(state=args.state)
    processed_count = 0
    commented_count = 0

    for pr in pulls:
        processed_count += 1
        try:
            is_contained = contains_all_pr_commits(repo, args.branch, pr)
        except Exception as compare_error:
            print(
                f"PR #{pr.number}: compare failed [{pr.base.ref} <- {pr.head.ref}]: {compare_error}",
                file=sys.stderr,
            )
            continue

        if is_contained:
            try:
                pr.create_issue_comment(args.status)
                commented_count += 1
                result = "commented"
            except Exception as comment_error:
                print(
                    f"PR #{pr.number}: contains all commits, but commenting failed: {comment_error}",
                    file=sys.stderr,
                )
                result = "comment_failed"
        else:
            result = "not_contained"

        print(
            f"PR #{pr.number} [{pr.base.ref} <- {pr.head.ref}] {pr.title!r}: "
            f"contained={is_contained} -> {result}"
        )

    print(
        f"Done. Processed {processed_count} PR(s); commented on {commented_count} PR(s)."
    )


if __name__ == "__main__":
    main()


