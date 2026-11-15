#!/bin/sh
# Get the Ubuntu sources tests/ reads, WITHOUT building anything.
#
#   ./fetch-sources.sh                    download them (needs deb-src)
#   ./fetch-sources.sh --from DIR         reuse .dsc files already on disk
#   ./fetch-sources.sh --have             exit 0 when they are extracted
#   ./fetch-sources.sh --into DIR         where to extract
#                                         (default: ~/.cache/raye/desktop-src)
#
# Then:
#   RAYE_DESKTOP_SRC=<dir> pytest tests/
#
# Why this exists. Thirty of the tests in tests/ read the source the
# series is applied to, and they skipped on every run with the reason
# "build.sh is the gate" -- a dead end: build.sh needs a resolute chroot
# and compiles two Plasma packages, which is hours, to answer a question
# that takes eight seconds. So the thirty had never run. They are correct
# and they all pass; what was missing was a cheap way to feed them.
#
# The version is checked against ./components, exactly as build.sh
# checks it. A patch that still applies to a newer source is not the same
# as a patch that is still right for it, and a test run against the wrong
# source is worse than no test: it is green for the wrong reason.
set -eu

here=$(cd "$(dirname "$0")" && pwd)
from=
# NOT inside the repository. /srv is a virtiofs share and a file written
# there from the build VM is born root:root, while the services that
# read /srv run as uid 1000 -- 196 MB of root-owned sources in the tree is
# the known way to break them. tests/test_build_guards.py also asserts that
# nothing lands in work/ or out/, for the same reason.
cache=${XDG_CACHE_HOME:-${HOME:+$HOME/.cache}}
into=${cache:-/var/tmp/raye-src}/raye/desktop-src

# the component names, comments and blank lines dropped
component_names() { sed 's/#.*//' "$here/components" | awk 'NF == 2 { print $1 }'; }

while [ $# -gt 0 ]; do
    case $1 in
    # For iso/tools/raye-tests: exit 0 when a tree for EVERY component is
    # there -- one of the two is not "the sources" -- and otherwise say in ONE
    # line what to run. The launcher lifts that line into its report, so the
    # remedy comes from the side that knows it instead of being typed into
    # the suite table and left to go stale.
    --have)
        missing=0
        for name in $(component_names); do
            [ -n "$(find "$into" -maxdepth 1 -mindepth 1 -type d -name "$name-*" \
                    2>/dev/null | head -1)" ] || missing=1
        done
        [ "$missing" = 0 ] && exit 0
        echo "thirty tests read the Ubuntu source: desktop/fetch-sources.sh" \
             "gets it without building anything (--help)" >&2
        exit 1 ;;
    --from) from=${2:?--from needs a directory}; shift 2 ;;
    --into) into=${2:?--into needs a directory}; shift 2 ;;
    --help) sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "usage: $0 [--from DIR] [--into DIR]" >&2; exit 2 ;;
    esac
done

die() { echo "$0: $*" >&2; exit 1; }
say() { printf '==> %s\n' "$*"; }

command -v dpkg-source >/dev/null || die "dpkg-source is missing (apt install dpkg-dev)"
mkdir -p "$into"
into=$(cd "$into" && pwd)
[ -n "$from" ] && from=$(cd "$from" && pwd)

got_any=0
while read -r name expected; do
    case ${name:-} in ''|'#'*) continue ;; esac
    [ -n "${expected:-}" ] || die "./components: no version for $name"
    got_any=1

    existing=$(find "$into" -maxdepth 1 -mindepth 1 -type d -name "$name-*" | head -1)
    if [ -n "$existing" ]; then
        say "$name: already extracted at $existing"
        continue
    fi

    if [ -n "$from" ]; then
        dsc=$(find "$from" -name "${name}_*.dsc" | sort | head -1)
        [ -n "$dsc" ] || die "no ${name}_*.dsc under $from"
    else
        command -v apt-get >/dev/null || die "no apt-get here; use --from DIR"
        hold=$into/.download/$name
        mkdir -p "$hold"
        say "$name: downloading the source"
        ( cd "$hold" && apt-get source --download-only "$name" >/dev/null 2>&1 ) || die \
"no source for $name. On a Raye machine the source groups ship off; turn them on here only:
    sudo sed -i 's/^Enabled: no\$/Enabled: yes/' /etc/apt/sources.list.d/ubuntu.sources
    sudo apt-get update"
        dsc=$(find "$hold" -name "${name}_*.dsc" | sort | head -1)
        [ -n "$dsc" ] || die "apt-get source left no .dsc for $name"
    fi

    got=$(sed -n 's/^Version: //p' "$dsc" | head -1)
    got_no_epoch=${got#*:}      # the epoch is Ubuntu's packaging, not the version the patches saw
    if [ "$got_no_epoch" != "$expected" ] && [ "${REBASE:-}" != 1 ]; then
        die "$name is $got_no_epoch, the patches were written for $expected.
    Rebase the series and record the new version in ./components. REBASE=1
    extracts it anyway, which is for trying a rebase, never for a verdict."
    fi

    say "$name $got_no_epoch: extracting"
    # --no-check skips the SIGNATURE of the .dsc, not the checksums of the
    # tarballs: those are still verified, which is what matters here. The
    # Ubuntu archive key is not on a Raye machine, and a .dsc left behind
    # by a build carries no signature at all.
    ( cd "$into" && dpkg-source --no-check -x "$dsc" >/dev/null )
done < "$here/components"

[ "$got_any" = 1 ] || die "./components lists nothing"

cat <<MSG

The sources are in $into. Now:

    RAYE_DESKTOP_SRC=$into pytest tests/
MSG
