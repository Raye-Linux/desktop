#!/bin/sh
# Builds Raye's own packages of the desktop: Ubuntu's sources with the Raye
# patch series on top, so what Raye changes lives in the desktop's code
# instead of in a layer of settings and scripts above it.
#
# Runs as root in a resolute system (a chroot is fine) with deb-src:
#
#   ./build.sh                 every component in ./components
#   ./build.sh plasma-desktop  one of them
#
#   JOBS=n       parallel compile jobs (default: nproc)
#   WORK=dir     where sources are unpacked (default: ./work)
#   REBASE=1     allow a source version other than the one in ./components
#   NOCHECK=1    skip the package's own test suite (never for a release)
#
# Output: ./out/*.deb
#
# The version becomes <ubuntu version>+raye<n>, so the package replaces
# Ubuntu's and says plainly where it came from.

set -eu
here=$(cd "$(dirname "$0")" && pwd)
work=${WORK:-$here/work}
# OUT is overridable like WORK. Without it, anything that runs build.sh --
# a test, a trial build -- leaves a folder in the repository, and a file created
# in /srv from the build machine is born root:root while the services that read
# /srv run as uid 1000. The default is unchanged: raye/iso's message still points
# at desktop/out.
out=${OUT:-$here/out}
jobs=${JOBS:-$(nproc)}
raye_revision=5

say() { printf '\033[1;35m==>\033[0m %s\n' "$*"; }
die() { echo "build.sh: $*" >&2; exit 1; }

[ "$(id -u)" = 0 ] || die "must run as root (it installs build dependencies)"
command -v dpkg-buildpackage > /dev/null || die "dpkg-dev is not installed"
command -v dpkg-source > /dev/null || die "dpkg-dev is not installed"

# A caller who runs out of memory reaches for -flto=N, and it breaks the ABI.
#
# Ubuntu's default flags carry `-flto=auto -ffat-lto-objects`, and with no make
# jobserver -- CMake's recipes do not get one -- every link forks nproc ltrans
# processes. On a 28-core VM with no swap that is how a build gets its lto1
# killed, so bounding it looks like the obvious move.
#
# It is the wrong move. Measured on 2026-11-06: appending `-flto=1` to override
# `-flto=auto` built plasma-workspace fine and then FAILED in dh_makeshlibs,
# because libtaskmanager6 had lost symbols its shipped .symbols file lists --
# the vtable of an abstract class, and shared_ptr template instantiations:
#
#   #MISSING: ...+raye1# _ZTVN11TaskManager23AbstractTasksModelIfaceE@Base
#
# One LTO partition lets GCC see the whole library at once and drop what it
# believes unused, so -flto=N changes the ABI SURFACE of the result. dpkg is
# right to refuse: a program built against the archive's library would then look
# for a symbol this one no longer has.
#
# And DPKG_GENSYMBOLS_CHECK_LEVEL=0 is not the answer either. It turns that
# refusal into a warning -- it HIDES the ABI change instead of undoing it.
#
# The bound that is ABI-neutral is JOBS: fewer links at once, Ubuntu's flags
# untouched. So this refuses the flag rather than letting a memory problem turn
# into a silent packaging one.
for raye_flagvar in DEB_CFLAGS_APPEND DEB_CXXFLAGS_APPEND DEB_LDFLAGS_APPEND \
                    DEB_CFLAGS_SET DEB_CXXFLAGS_SET DEB_LDFLAGS_SET; do
    eval "raye_flagval=\${$raye_flagvar:-}"
    case " $raye_flagval " in
        *" -flto="*|*" -flto-partition="*|*"-flto="*)
            die "$raye_flagvar carries an -flto setting ($raye_flagval).
    Overriding Ubuntu's -flto=auto changes which symbols the libraries export,
    and dh_makeshlibs then fails on the shipped .symbols file -- measured, see
    the comment above this check. Bound the memory with JOBS instead:
        JOBS=10 $0 ${*:-}" ;;
    esac
done
unset raye_flagvar raye_flagval

# the components asked for, or all of them
wanted=${*:-}

build_one() {
    source_package=$1
    expected=$2
    series=$here/patches/$source_package

    say "Getting Ubuntu's source of $source_package"
    mkdir -p "$work" "$out"
    cd "$work"
    rm -rf "$source_package-build"
    mkdir "$source_package-build"
    cd "$source_package-build"
    # A Raye image ships the deb-src groups of ubuntu.sources "Enabled: no",
    # on purpose: turned on, every machine fetches 18 MiB of source indexes at
    # every apt update, 16 of them for resolute/universe alone. Ubuntu's own
    # ubuntu.sources does the same. So on a Raye machine this is the normal
    # first failure, and the message has to say how to get past it -- "is
    # deb-src enabled?" alone sends people looking in the wrong file. The
    # versions this tree builds against live in resolute-updates, not in
    # resolute, so the -updates groups are the ones that matter.
    apt-get source "$source_package" > /dev/null 2>&1 || die \
"no source for $source_package. On a Raye machine the source groups ship off; turn them on here only:
    sudo sed -i 's/^Enabled: no\$/Enabled: yes/' /etc/apt/sources.list.d/ubuntu.sources
    sudo apt-get update"

    dsc=$(ls ./*.dsc 2>/dev/null | head -1)
    [ -n "$dsc" ] || die "apt-get source left no .dsc for $source_package"
    got=$(sed -n 's/^Version: //p' "$dsc" | head -1)
    # the epoch is Ubuntu's packaging, not the version the patches saw
    got_no_epoch=${got#*:}
    if [ "$got_no_epoch" != "$expected" ] && [ "${REBASE:-}" != 1 ]; then
        die "$source_package is $got_no_epoch, the patches were written for $expected.
    Rebase the series, record the new version in ./components, and run the
    tests again. REBASE=1 builds it anyway, which is for trying a rebase,
    never for a release."
    fi

    tree=$(ls -d ./*/ | head -1)
    cd "$tree"

    say "Applying the Raye series"
    applied=0
    if [ -d "$series" ]; then
        for patch in "$series"/*.patch; do
            [ -e "$patch" ] || continue
            patch -p1 --silent --dry-run < "$patch" ||
                die "does not apply: $(basename "$patch")"
            patch -p1 --silent < "$patch"
            applied=$((applied + 1))
            printf '    %s\n' "$(basename "$patch")"
        done
    fi
    [ "$applied" -gt 0 ] || die "no patch in $series: nothing would tell this
    package apart from Ubuntu's, and installing it would only shadow the
    archive's own."

    say "Recording the version"
    new_version="$got+raye$raye_revision"
    name=$(dpkg-parsechangelog -S Source)
    tmp=$(mktemp)
    {
        printf '%s (%s) resolute; urgency=medium\n\n' "$name" "$new_version"
        printf '  * Raye: %s patch(es) from the Raye desktop series.\n' "$applied"
        for patch in "$series"/*.patch; do
            [ -e "$patch" ] || continue
            printf '    - %s\n' "$(basename "$patch" .patch)"
        done
        printf '\n -- Raye Linux <bonjour@rayelinux.com>  %s\n\n' "$(date -R)"
        cat debian/changelog
    } > "$tmp"
    mv "$tmp" debian/changelog

    say "Installing build dependencies"
    DEBIAN_FRONTEND=noninteractive apt-get build-dep -y --no-install-recommends . \
        > /dev/null || die "could not install the build dependencies"

    say "Building $name $new_version with $jobs jobs"
    if [ "${NOCHECK:-}" = 1 ]; then
        echo "    WITHOUT the package's test suite (NOCHECK=1)"
        build_options="parallel=$jobs nocheck"
    else
        build_options="parallel=$jobs"
    fi
    DEB_BUILD_OPTIONS="$build_options" dpkg-buildpackage -b -uc -us

    cd ..
    count=$(ls ./*.deb 2>/dev/null | wc -l)
    [ "$count" -gt 0 ] || die "the build produced no .deb"
    mv ./*.deb "$out/"
    say "$count package(s) in $out"
}

# A name that is not in ./components must NOT build nothing and say "Done".
# Measured on 2026-11-06: `./build.sh --aucun-composant` printed "Done" and
# exited 0 having built not one package -- the same shape as every other defect
# this tree has paid for, a command that succeeds without doing the work. A
# typo in a release script would then produce an image with the archive's
# desktop in it and nothing to say so.
if [ -n "$wanted" ]; then
    # tr: one SPACE-separated line. With newlines between the names the
    # `case` pattern below (which looks for " name ") matches nothing, and every
    # component -- including a correct one -- is refused. Caught by running it.
    known=$(sed 's/#.*//' "$here/components" | awk 'NF {print $1}' | tr '\n' ' ')
    for asked in $wanted; do
        case " $known " in
            *" $asked "*) ;;
            *) die "$asked is not a component of this tree. The components are:
$(printf '    %s\n' $known)" ;;
        esac
    done
fi

built=0
while read -r source_package expected; do
    case $source_package in ''|\#*) continue ;; esac
    [ -z "$wanted" ] || case " $wanted " in *" $source_package "*) ;; *) continue ;; esac
    build_one "$source_package" "$expected"
    built=$((built + 1))
done < "$here/components"

# the loop runs in this shell, so the counter survives it; a components file
# that is empty or all comments would otherwise be another silent success
[ "$built" -gt 0 ] || die "nothing was built: ./components names no component"

say "Done ($built component(s))"
