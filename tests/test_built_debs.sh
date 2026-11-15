#!/bin/bash
#
# Checks the .deb files this repository's build.sh produced, before an image
# is built from them.
#
#   tests/test_built_debs.sh <folder of .deb>     (default /var/tmp/raye/desktop-debs)
#   tests/test_built_debs.sh --self-test
#
# Exit 0 when everything holds, 1 otherwise.
#
# Why a check between the two builds, and not only the tests inside each.
#
# The package build already proves the patch where it is compiled: plasma-
# workspace runs `ctest -R '^raye'` in override_dh_auto_test. What NO test in
# this repository can see is whether the property survived into the .deb --
# whether the file landed in the binary package the image installs, and whether
# the packaging field that lets anything OUTSIDE this repository require it is
# really in the control data rather than only in debian/control.
#
# That gap has a measured cost. On 2026-11-05 the image was built from
# plasma-desktop .deb dated 00:27 while the patch that adds
# `Provides: raye-desktop-layout` was committed at 21:12: the source said one
# thing and the packages shipped another, and nothing between them said so. An
# image built from stale .deb is indistinguishable from a correct one until a
# new account logs in and finds no taskbar.
#
# So every check here reads the BUILT ARTEFACT -- dpkg-deb on the file --
# never debian/control in the tree. Reading the tree would pass while the .deb
# on disk is the old one, which is exactly the failure this file exists for.

set -uo pipefail
here=$(cd "$(dirname "$0")/.." && pwd)
# An OPTION is not a folder. `debs=${1:-...}` took `--self-test` for the
# folder of packages, so --self-test ran its cases against a path that does not
# exist: two of them printed "SAUTE (pas de plasma-desktop*.deb dans
# --self-test)" and set ok_all=0, which means the self-test could NEVER pass.
# A self-test that is always red proves no more than one that is always green,
# and it had been that way since the file was written. Found 2026-11-07 by a
# new case that failed for this reason and not its own.
case "${1:-}" in
    -*) debs=/var/tmp/raye/desktop-debs ;;
    *)  debs=${1:-/var/tmp/raye/desktop-debs} ;;
esac

# `dpkg-deb -c FILE | grep -q PATTERN` is a FALSE NEGATIVE under pipefail,
# and it cost this file its first green run. grep -q exits the moment it finds
# a match and closes the pipe; dpkg-deb then dies of SIGPIPE with a non-zero
# status, and `set -o pipefail` reports the PIPELINE as failed -- so a package
# that really does contain the file is reported as not containing it. The two
# checks below said "plasma-workspace does not carry /usr/bin/plasmashell" and
# "plasma-desktop-data does not contain layout.js" about packages that carry
# both, measured by hand right after.
#
# So the list is read ONCE into a variable and matched there: no pipe, no
# SIGPIPE, and the same string is available to every check.
contents_of() { dpkg-deb -c "$1" 2>/dev/null; }
holds_path() {
    # $1: the .deb contents as one string, $2: the path without a leading ./
    case "
$1" in *"
"*" ./$2
"*) return 0 ;; esac
    printf '%s' "$1" | grep -q -- " \./$2\$" && return 0
    return 1
}

LAYOUT_PROVIDES=raye-desktop-layout
# where libplasma reads a layout that belongs to the desktop itself
LAYOUT_PATH=usr/share/plasma/shells/org.kde.plasma.desktop/contents/layout.js

fail=0
err() { echo "FAIL: $*"; fail=1; }
ok()  { echo "ok:   $*"; }

# the one binary package that may claim to ship the Raye layout
find_provider() {
    local d p
    for d in "$1"/*.deb; do
        [ -e "$d" ] || continue
        case "$d" in *-dbgsym_*|*.ddeb) continue ;; esac
        p=$(dpkg-deb -f "$d" Provides 2>/dev/null)
        case ",${p// /}," in *",$LAYOUT_PROVIDES,"*) echo "$d" ;; esac
    done
}

check_there_are_debs() {
    local n
    n=$(ls "$1"/*.deb 2>/dev/null | grep -cv -e '-dbgsym_' -e '\.ddeb$')
    [ "${n:-0}" -gt 0 ] ||
        err "no .deb in $1: there is nothing to check, and an image built now would carry the previous build's packages"
    [ "${n:-0}" -eq 0 ] || ok "$n package(s) to check in $1"
}

# The component list is read from ./components, not written out: a third
# component added there without a .deb would otherwise go unnoticed, and the
# image would install the archive's package for it in silence.
check_every_component_was_built() {
    local src _v found d name
    while read -r src _v; do
        case $src in ''|\#*) continue ;; esac
        found=0
        for d in "$1"/*.deb; do
            [ -e "$d" ] || continue
            case "$d" in *-dbgsym_*|*.ddeb) continue ;; esac
            name=$(dpkg-deb -f "$d" Source 2>/dev/null)
            # a binary whose name equals the source has no Source field
            [ -n "$name" ] || name=$(dpkg-deb -f "$d" Package 2>/dev/null)
            # Source may carry a version in brackets: "plasma-workspace (4:6.6.6)"
            name=${name%% *}
            [ "$name" = "$src" ] && { found=1; break; }
        done
        [ "$found" = 1 ] && ok "$src was built" ||
            err "./components asks for $src and no .deb in $1 comes from it: the image would install the archive's $src instead, silently"
    done < "$here/components"
}

check_the_version_says_raye() {
    local d v bad=0
    for d in "$1"/*.deb; do
        [ -e "$d" ] || continue
        case "$d" in *-dbgsym_*|*.ddeb) continue ;; esac
        v=$(dpkg-deb -f "$d" Version 2>/dev/null)
        case "$v" in *+raye*) ;; *) err "$(basename "$d") is version $v: without +raye<n> it does not sort above the archive's own package, and apt would keep Ubuntu's"; bad=1 ;; esac
    done
    [ "$bad" = 1 ] || ok "every package sorts above the archive (+raye<n>)"
}

check_one_package_provides_the_layout() {
    local provs n
    mapfile -t provs < <(find_provider "$1")
    n=${#provs[@]}
    if [ "$n" -eq 0 ]; then
        err "no built package declares Provides: $LAYOUT_PROVIDES. raye-theme depends on that name, so apt would REFUSE to install the look -- and before that dependency existed it installed happily and gave a first login with no taskbar"
        return
    fi
    [ "$n" -eq 1 ] || { err "$n packages claim Provides: $LAYOUT_PROVIDES; only the one that really ships the layout may"; return; }
    ok "$(basename "${provs[0]}") declares Provides: $LAYOUT_PROVIDES"
}

# The check that matters, and the one a rebase breaks without a word: the
# CLAIM and the FILE have to be in the same binary package. Ubuntu moves a
# directory between packages often enough, and dh_install globs mean the only
# way to know which one took it is to look inside the .deb.
check_the_claimer_really_ships_it() {
    local provs d
    mapfile -t provs < <(find_provider "$1")
    [ "${#provs[@]}" -eq 1 ] || return
    d=${provs[0]}
    local listing
    listing=$(contents_of "$d")
    if holds_path "$listing" "$LAYOUT_PATH"; then
        ok "$(basename "$d") really ships /$LAYOUT_PATH"
    else
        err "$(basename "$d") claims $LAYOUT_PROVIDES but does NOT contain /$LAYOUT_PATH: the name is satisfied by a package with no layout, which is worse than no dependency at all"
    fi
}

# The look-and-feel lookup fix lives in the shell binary. A .deb that does not
# carry the shell cannot carry the fix, so name the package and the file rather
# than trusting that "plasma-workspace was built".
check_the_shell_is_in_the_workspace_package() {
    local d found=0 listing
    for d in "$1"/plasma-workspace_*.deb; do
        [ -e "$d" ] || continue
        # found marks that the PACKAGE EXISTS, not that the check passed. In
        # the first version only the success branch set it, so a single failure
        # printed a second, FALSE message -- "no plasma-workspace_*.deb" about a
        # file sitting right there. A wrong diagnosis is worse than none.
        found=1
        listing=$(contents_of "$d")
        if holds_path "$listing" "usr/bin/plasmashell"; then
            ok "$(basename "$d") carries /usr/bin/plasmashell (where the layout lookup lives)"
        else
            err "$(basename "$d") does not carry /usr/bin/plasmashell: the layout lookup fix is not in this package"
        fi
    done
    [ "$found" = 1 ] ||
        err "no plasma-workspace_*.deb in $1: the layout lookup fix is a patch to the shell, so without it the image carries the archive's shell and the fix is absent"
}

# the source package a built .deb came from, by the same rule
# check_every_component_was_built uses (a binary whose name equals the source
# has no Source field, and Source may carry a version in brackets)
deb_source() {
    local name
    name=$(dpkg-deb -f "$1" Source 2>/dev/null)
    [ -n "$name" ] || name=$(dpkg-deb -f "$1" Package 2>/dev/null)
    printf '%s' "${name%% *}"
}

# the basenames a patch ADDS that a package is expected to install
added_resources_of() {
    awk '
        /^--- / { prev = $2 }
        /^\+\+\+ / {
            if (prev == "/dev/null") {
                f = $2; sub(/^b\//, "", f)
                if (f ~ /\/(autotests|raye-autotests|tests)\//) next
                if (f ~ /\.(qml|js)$/) { n = f; sub(/.*\//, "", n); print n }
            }
        }
    ' "$1"
}

# The six checks above all read the artefact, which is right -- and not one
# of them reads the SERIES. On 2026-11-07 they were all green over a
# plasma-workspace built two patches earlier: this file's own header names the
# stale-.deb defect of 2026-11-05 as its reason to exist, and it had no check
# for it. A gate that documents the defect it exists for and does not measure
# it is worse than no gate, because its green is believed.
#
# What to look for is derived from patches/, never written here: every patch
# that ADDS an installed resource (.qml or .js outside an autotests/ or tests/
# folder) must have put it into a package built from its own source. A list of
# names here would go stale the day a patch is added -- which is the exact
# shape of the thing being guarded.
#
# The probe is `dpkg-deb --fsys-tarfile ... | grep -a`, and both halves are
# measured, not chosen:
#
#   --fsys-tarfile reads the payload as a BYTE STREAM, so it finds the name
#   whether it is a file path or a COMPILED RESOURCE. Plasma 6 puts applet QML
#   through plasma_add_applet(QML_SOURCES ...), which compiles it into the
#   applet's .so -- `dpkg-deb -c` lists no such file. Measured 2026-11-07:
#   RayeTrayMetrics.qml appears nowhere in `dpkg-deb -c` of a package that
#   carries it, and a path-only check would have called a correct build broken.
#
#   grep -a is not decoration. On that same .so, `grep -c` printed NOTHING
#   while `grep -ac` printed 2: without -a, grep gives up on a binary and the
#   probe reads as "absent". That is a false RED on every build.
#
# Proven on the real pair, same probe, same name: the package of 2026-11-06
# 01:30 gives 0, the one built after the patch gives 2.
check_the_series_reached_the_packages() {
    local src _v p name d looked=0 shipped=0 found hits
    while read -r src _v; do
        case $src in ''|\#*) continue ;; esac
        [ -d "$here/patches/$src" ] || continue
        for p in "$here/patches/$src"/*.patch; do
            [ -e "$p" ] || continue
            for name in $(added_resources_of "$p"); do
                looked=$((looked + 1))
                found=0
                for d in "$1"/*.deb; do
                    [ -e "$d" ] || continue
                    case "$d" in *-dbgsym_*|*.ddeb) continue ;; esac
                    [ "$(deb_source "$d")" = "$src" ] || continue
                    # `| grep -aq` here is the FALSE NEGATIVE this file's own
                    # header warns about, and it was written anyway on
                    # 2026-11-07: grep -q exits at the first match, dpkg-deb
                    # dies of SIGPIPE with status 2, and `set -o pipefail`
                    # hands that 2 to the `if`. The check then reported a
                    # package that really carries the file as not carrying it.
                    # Measured: rc=2 inside this script, rc=0 for the same
                    # command outside it, and grep printed NOTHING either way
                    # -- a tool error that reads exactly like a "no".
                    # `grep -ac` has no early exit, so dpkg-deb reaches the end
                    # of its stream and nothing is killed; `|| true` is for
                    # grep's own 1 on a count of zero, which is an answer, not
                    # a failure.
                    hits=$(dpkg-deb --fsys-tarfile "$d" 2>/dev/null | grep -ac -- "$name" || true)
                    if [ "${hits:-0}" -gt 0 ]; then
                        found=1; break
                    fi
                done
                if [ "$found" = 1 ]; then
                    shipped=$((shipped + 1))
                else
                    err "$(basename "$p") adds $name and no $src package in $1 contains it: these packages are older than the patch series, and an image built from them would not carry this patch"
                fi
            done
        done
    done < "$here/components"

    # "one is not zero", and zero is not a pass. A series whose patches add
    # no installed resource -- or a rename that makes added_resources_of match
    # nothing -- would leave this check with nothing to say, and saying nothing
    # here looks exactly like saying yes.
    if [ "$looked" = 0 ]; then
        err "no patch in patches/ adds an installed .qml or .js, so this check measured NOTHING: either the series really adds none (then this check is dead and should be removed, not left green) or added_resources_of no longer matches the paths it used to"
    else
        [ "$shipped" = "$looked" ] &&
            ok "every patch that adds an installed resource shipped it ($shipped of $looked)"
    fi
}

self_test() {
    local t ok_all=1 d
    t=$(mktemp -d)

    # 1. an empty folder: the analysis must not go quietly green
    mkdir -p "$t/vide"
    (fail=0; check_there_are_debs "$t/vide"; exit $fail) >/dev/null &&
        { echo "self-test: dossier vide non signale"; ok_all=0; }

    # 2. a component with no package of its own -- the 2026-11-05 defect
    mkdir -p "$t/partiel"
    for d in "$debs"/plasma-desktop*.deb; do [ -e "$d" ] && cp "$d" "$t/partiel/"; done
    if ls "$t/partiel"/*.deb >/dev/null 2>&1; then
        (fail=0; check_every_component_was_built "$t/partiel"; exit $fail) >/dev/null &&
            { echo "self-test: composant non construit non attrape"; ok_all=0; }
    else
        echo "self-test: SAUTE (pas de plasma-desktop*.deb dans $debs pour fabriquer le cas)"
        ok_all=0
    fi

    # 3. nothing provides the layout name
    mkdir -p "$t/sans-provides"
    for d in "$debs"/plasma-workspace_*.deb; do [ -e "$d" ] && cp "$d" "$t/sans-provides/"; done
    if ls "$t/sans-provides"/*.deb >/dev/null 2>&1; then
        (fail=0; check_one_package_provides_the_layout "$t/sans-provides"; exit $fail) >/dev/null &&
            { echo "self-test: absence de Provides non attrapee"; ok_all=0; }
    else
        echo "self-test: SAUTE (pas de plasma-workspace_*.deb dans $debs)"
        ok_all=0
    fi

    # 4. a series that adds no installed resource at all: the check must not
    #    go quietly green on having measured NOTHING. "one is not zero", and
    #    zero is not a pass -- a rename of patches/ or of the path shapes
    #    added_resources_of matches would otherwise leave this check mute,
    #    and mute reads exactly like yes.
    mkdir -p "$t/rien/patches/plasma-workspace"
    printf 'plasma-workspace 1\n' > "$t/rien/components"
    printf -- '--- /dev/null\n+++ b/startkde/raye-autotests/tst_x.cpp\n' \
        > "$t/rien/patches/plasma-workspace/0001-adds-only-a-test.patch"
    (here="$t/rien"; fail=0; check_the_series_reached_the_packages "$debs"; exit $fail) >/dev/null &&
        { echo "self-test: serie qui n ajoute aucune ressource installee non signalee"; ok_all=0; }

    # 5. The FALSE NEGATIVE direction, and it is the one that actually
    #    happened. On 2026-11-07 this check was first written with
    #    `| grep -aq`, which under this file's own `set -o pipefail` makes
    #    dpkg-deb die of SIGPIPE and hands ITS status to the test: a package
    #    that does carry the file was reported as not carrying it. Every other
    #    check stayed green, so the gate read as having found a real defect in
    #    a correct build.
    #
    #    It is run against the REAL series and the REAL packages, and not
    #    against a fabricated one-patch series, because the bug is
    #    position-dependent: it only bites when grep's match comes early
    #    enough that dpkg-deb is still writing. Measured 2026-11-07 -- a
    #    fabricated case naming CompactApplet.qml passed even with the bug in
    #    place, because an earlier package in the loop matched it cleanly and
    #    satisfied the check before the failing one was reached. A case that
    #    cannot fail is not a case.
    if ls "$debs"/plasma-workspace_*.deb >/dev/null 2>&1; then
        (fail=0; check_the_series_reached_the_packages "$debs"; exit $fail) >/dev/null ||
            { echo "self-test: faux negatif -- la serie reelle et les paquets reels se contredisent"; ok_all=0; }
    else
        echo "self-test: SAUTE (pas de plasma-workspace_*.deb dans $debs)"
        ok_all=0
    fi

    rm -rf "$t"
    [ "$ok_all" = 1 ] && echo "self-test ok"
    [ "$ok_all" = 1 ]
}

case "${1:-}" in
    --self-test) self_test; exit $? ;;
    -h|--help) sed -n '3,9p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
esac

command -v dpkg-deb >/dev/null ||
    { echo "skipped: dpkg-deb is not installed" >&2; exit 77; }
# 77 is the skip code, not 2. This tree already uses it in four tests, and
# iso/tools/raye-tests reads it as a skip with the last line as the reason. A
# machine that has simply never built the packages must not look like a red
# suite: a red that means nothing is a red that gets ignored.
[ -d "$debs" ] ||
    { echo "skipped: no $debs, the desktop packages have not been built here" >&2; exit 77; }

echo "== $debs"
check_there_are_debs "$debs"
check_every_component_was_built "$debs"
check_the_version_says_raye "$debs"
check_one_package_provides_the_layout "$debs"
check_the_claimer_really_ships_it "$debs"
check_the_shell_is_in_the_workspace_package "$debs"
check_the_series_reached_the_packages "$debs"
echo
[ "$fail" = 0 ] && echo "ok: les .deb construits portent vraiment le correctif et sa declaration"
exit "$fail"
