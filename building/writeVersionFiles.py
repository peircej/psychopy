#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""Writes the current version, build platform etc.
"""
from subprocess import run
import pathlib
from packaging import version

root = pathlib.Path(__file__).parent.parent  # root of the repo

def _call(cmd, verbose=False):
    result = run(cmd, capture_output=True, text=True)
    if verbose or result.returncode or result.stderr:
        print(f"Call:\n  {' '.join(cmd)}")
        print(f"Resulted in:\n  {result.stdout + result.stderr}")
        return None
    else:
        return result.stdout.strip()

def _checkValidVersion(v):
    """Check if version string is valid and return True/False"""
    try:
        version.Version(v)
    except version.InvalidVersion:
        print(f"Invalid version: {v}")
        return False
    return True

def countSince(ref):
    """Get number of commits since given commit/tag"""
    cmd = ['git', 'rev-list', '--count', ref + '..HEAD']
    return _call(cmd)

def getLastCommit(filepath=None):
    """Get SHA of last commit that touched given file or last commit in repo"""
    if filepath:
        cmd = ['git', 'log', '-n', '1', '--pretty=format:%H', filepath]
    else:
        cmd = ['git', 'log', '-n', '1', '--pretty=format:%H']
    return _call(cmd)

def getBranch():
    """Get current branch name"""
    cmd = ['git', 'rev-parse', '--abbrev-ref', 'HEAD']
    resp = _call(cmd)
    if resp is None:
        return ''
    return resp

def getTags():
    """Get list of tags"""
    cmd = ['git', 'tag', '--sort=-v:refname']
    resp = _call(cmd)
    if resp is None:
        return []
    return resp.split()

def isShallowRepo():
    """Check if git repo is shallow (or not a repo)"""
    cmd = ['git', 'rev-parse', '--is-shallow-repository']
    resp = _call(cmd)
    return resp is None or resp=='true'

def makeVersionSuffix(base):
    """Makes version suffix like post3 or dev8 given base version number
    
    Suffix checks for a tag matching the base and then counts commits since
    either that tag or the last commit that touched the VERSION file.
    
    Choice of post/dev is based on whether we're on the release branch."""
    if isShallowRepo():
        print("Can't calculate good version number in shallow repo. "
              "Did you fetch with `git clone --depth=1`?\n"
              f"Using simple version number ({base})")
        return ''
    if base in getTags():
        nCommits = countSince(base)
        if nCommits == '0':
            return ''  # we're on a tag
    else:
        nCommits = countSince(getLastCommit(root/'psychopy/VERSION'))
    branch = getBranch()
    if branch=='release':
        return f'post{nCommits}'
    else:
        return f'dev{nCommits}'
    
def updateVersionFile():
    """Take psychopy/VERSION, append the branch and distance to commit
    and update the VERSION file accordingly"""
    raw = (root/'psychopy/VERSION').read_text().strip()
    try:
      origVersion = version.Version(raw)
    except version.InvalidVersion:
        raise version.InvalidVersion("Can't create valid version from invalid starting point:\n"
                                     "  {raw}")
    base = origVersion.base_version  # removing things like the dev21 or post3
    suffix = makeVersionSuffix(base)
    final = base + suffix
    if final != raw:
        with open(root/'psychopy/VERSION', 'w') as f:
            f.write(final)
        print(f"Updated version file to {final}")

def updateGitShaFile(sha=None):
    """Create psychopy/GIT_SHA

    :param:`dist` can be:
        None:
            writes __version__
        'sdist':
            for python setup.py sdist - writes git id (__git_sha__)
        'bdist':
            for python setup.py bdist - writes git id (__git_sha__)
            and __build_platform__
    """
    shaPath = root/"psychopy/GIT_SHA"
    if sha is None:
        sha = getLastCommit() or 'n/a'
    with open(shaPath, 'w') as f:
        f.write(sha)
    print(f"Created file: {shaPath.absolute()}")

if __name__ == "__main__":
    updateGitShaFile()
    updateVersionFile()
