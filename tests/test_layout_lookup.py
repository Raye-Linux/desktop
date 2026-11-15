"""That a new account is handed the desktop's layout, not a look's.

patches/plasma-desktop/0003 moved the default layout into the shell
package's contents/layout.js, and it was never read: ShellCorona asks the
active look-and-feel package first, KPackage answers that question out of
the package's *fallback*, and shell/packageplugins/lookandfeel makes that
fallback org.kde.breeze.desktop for every look but Breeze. All three
Breeze packages ship layouts/org.kde.plasma.desktop-layout.js, so the
answer was never empty and `defaultlayout` was unreachable.

🚨 This file reads both ends of that, because either one alone is a
silence:

  * the *fix*, in the patched plasma-workspace source -- a rebase that
    takes upstream's line back is the failure;
  * the *reason*, also in the source -- the fallback to Breeze, and
    Breeze's layout file. The day upstream drops either, this patch guards
    nothing, and that should be said out loud rather than carried for
    years as a correction nobody can explain.

    ./fetch-sources.sh && pytest tests/
"""
import re

import pytest

from conftest import components, needs_source, series

LAYOUT_FILE = "org.kde.plasma.desktop-layout.js"
BREEZE = "org.kde.breeze.desktop"


# ---------------------------------------------------------------- the series
# No source needed: these read the patch text, and they are the rule 0003
# argued for -- the shape of the desktop is not part of a look.

def test_no_patch_puts_a_layout_back_inside_a_look():
    # Shipping layouts/ from the Raye look-and-feel package would "fix" the
    # symptom and undo 0003: the layout would travel with the colours again,
    # and any look but Raye's would hand the account somebody else's desktop.
    #
    # Only the *paths* a patch touches are read, never its text. The first
    # version of this read every added line and failed on the patch header
    # that explains the bug, because the explanation names the file. A check
    # that forbids the documentation it exists to protect is worse than none
    # -- the same mistake raye/theme already made once with kwinrc comments.
    for component in components():
        for patch in series(component):
            touched = re.findall(r"^\+\+\+ b/(\S+)", patch.read_text(), re.M)
            for path in touched:
                assert not path.endswith(f"layouts/{LAYOUT_FILE}"), (
                    f"{patch.name} ships {path}: that is the shape of the "
                    "desktop going back inside a theme, which is what "
                    "plasma-desktop/0003 took it out of")


def test_the_shell_package_still_owns_a_layout_to_reach():
    # The whole point of the plasma-workspace patch is that *this* file
    # becomes reachable. If plasma-desktop's series stopped shipping it, the
    # lookup would be fixed and there would be nothing at the end of it.
    shipped = any(
        "+++ b/desktoppackage/contents/layout.js" in patch.read_text()
        for patch in series("plasma-desktop"))
    assert shipped, (
        "no patch of plasma-desktop ships desktoppackage/contents/layout.js: "
        "the shell package has no layout for the corrected lookup to find, and "
        "a new account would start with no layout at all")


# ----------------------------------------------------------------- the source
# These need a tree with the series applied, so each carries @needs_source:
# the two checks above read the patch text and must run everywhere.

@pytest.fixture(scope="module")
def plasma_workspace(patched):
    return patched("plasma-workspace")


@pytest.fixture(scope="module")
def load_default_layout(plasma_workspace):
    """The code of ShellCorona::loadDefaultLayout(), its // comments removed.

    ⚠️ The comments are stripped on purpose, and it is not tidiness. Both
    checks below count occurrences, and the patch *explains itself* in
    comments right where it changes the lookup: counting those made a
    two-call-site function read as three. It is the same mistake as reading
    a patch's prose for the file it ships -- a check has to read the code it
    is about.
    """
    text = (plasma_workspace / "shell/shellcorona.cpp").read_text()
    body = re.search(r"void ShellCorona::loadDefaultLayout\(\)\s*\{(.*?)\n\}\n", text, re.S)
    assert body, "ShellCorona::loadDefaultLayout() is not there any more"
    return "\n".join(re.sub(r"//.*$", "", line) for line in body.group(1).splitlines())


@pytest.fixture(scope="module")
def helper(plasma_workspace):
    return (plasma_workspace / "shell/lookandfeellayout.h").read_text()


@needs_source
def test_the_lookup_no_longer_asks_kpackage_for_a_layout(load_default_layout):
    # the line this patch replaces, in both places it appeared
    assert 'filePath("layouts"' not in load_default_layout, (
        "loadDefaultLayout() asks KPackage for a layout again. KPackage answers "
        f"out of the fallback to {BREEZE}, which ships one, so the shell "
        "package's defaultlayout is unreachable and a new account gets "
        "upstream's taskbar")


@needs_source
def test_the_lookup_asks_the_active_package_itself(load_default_layout):
    assert load_default_layout.count("ownLookAndFeelLayout(") == 2, (
        "both the layout and the pre-layout lookups must go through "
        "ownLookAndFeelLayout(): the pre-layout one has the same flaw, latent "
        "only because Breeze ships no prelayout today")


@needs_source
def test_the_shell_packages_layout_is_still_the_last_word(load_default_layout):
    assert 'kPackage().filePath("defaultlayout")' in load_default_layout, (
        "the shell package's own layout is no longer the fallback of the "
        "lookup, so correcting the first half gained nothing")


@needs_source
def test_the_helper_refuses_a_path_outside_the_active_package(helper):
    assert "startsWith(root)" in helper, (
        "nothing checks that the layout found is inside the active look-and-feel "
        "package, which is the only thing that tells its own file from the "
        "fallback's")


@needs_source
def test_the_helper_guards_the_empty_path_on_its_own(helper):
    # load-bearing, and measured: QString::startsWith(QString()) is true for
    # every string, and an invalid look-and-feel package has an empty path()
    # while filePath() still answers out of the fallback. Without this the
    # prefix test lets Breeze's layout through on that path alone.
    assert "root.isEmpty()" in helper and "isValid()" in helper, (
        "the helper does not refuse an empty path() on its own: startsWith() "
        "against an empty prefix is true for everything, so an invalid "
        "look-and-feel package would be handed the fallback's layout")


@needs_source
def test_the_reason_for_the_patch_is_still_true(plasma_workspace):
    # If upstream stops giving look-and-feel packages a Breeze fallback,
    # this patch guards nothing. Fail loudly then, rather than keep it.
    structure = (plasma_workspace / "shell/packageplugins/lookandfeel/lookandfeel.cpp").read_text()
    assert BREEZE in structure and "setFallbackPackage" in structure, (
        f"the look-and-feel package structure no longer falls back to {BREEZE}: "
        "this patch may no longer be needed -- check before keeping it")
    assert 'addDirectoryDefinition("layouts"' in structure, (
        'the look-and-feel structure no longer defines "layouts": the lookup '
        "this patch corrects cannot resolve anything, so check what replaced it")


@needs_source
def test_breeze_is_what_the_fallback_hands_over(plasma_workspace):
    # the other half of the reason: a fallback only bites because the package
    # it points at really ships the file
    looks = sorted((plasma_workspace / "lookandfeel").glob("org.kde.breeze*"))
    assert looks, "no Breeze look-and-feel package in the tree any more"
    shipping = [d.name for d in looks if (d / "contents/layouts" / LAYOUT_FILE).is_file()]
    assert shipping, (
        "no Breeze look-and-feel package ships "
        f"layouts/{LAYOUT_FILE} any more: the fallback has nothing to hand over, "
        "so check whether this patch is still needed")


# ------------------------------------------- who may claim to ship the layout
# Until the Provides below existed, the only thing stopping `apt install
# raye-theme` on an upstream plasma-desktop was raye/iso's image build, and
# that first login had no taskbar at all -- worse than the upstream bar this
# patch is about. The dependency cannot name plasma-desktop-data, because
# Ubuntu's own build of it satisfies that name and carries no layout; it names
# a virtual package only Raye's build declares.

LAYOUT_PROVIDES = "raye-desktop-layout"


def _paragraphs(control):
    out = []
    for chunk in control.split("\n\n"):
        fields = {}
        for line in chunk.splitlines():
            if line.startswith("#") or line.startswith((" ", "\t")):
                continue
            key, sep, value = line.partition(":")
            if sep:
                fields[key.strip()] = value.strip()
        if "Package" in fields:
            out.append(fields)
    return out


@pytest.fixture(scope="module")
def plasma_desktop(patched):
    return patched("plasma-desktop")


@needs_source
def test_one_package_claims_to_ship_the_raye_layout(plasma_desktop):
    declaring = [p["Package"] for p in _paragraphs((plasma_desktop / "debian/control").read_text())
                 if LAYOUT_PROVIDES in p.get("Provides", "")]
    assert declaring, (
        f"no binary package declares Provides: {LAYOUT_PROVIDES}, so nothing "
        "outside this repository can require that a Raye layout is installed: "
        "raye-theme on an upstream plasma-desktop gives a first login with no "
        "taskbar at all")
    assert len(declaring) == 1, (
        f"{declaring} all claim to ship the Raye layout; only the one that "
        "really does may")


@needs_source
def test_the_package_that_claims_it_is_the_one_that_ships_it(plasma_desktop):
    # The check that matters, and the one a rebase breaks silently: the
    # claim and the file have to be in the same binary package. Ubuntu moves
    # a directory between packages often enough, and dh_install globs mean
    # reading the .install is the only way to know which one takes it.
    from fnmatch import fnmatch

    # plasma_install_package(dir component [root] [type]) hands libplasma's
    # macro down to kpackage_install_package, which installs under
    # share/<PLASMA_RELATIVE_DATA_INSTALL_DIR>/<root>/<component> -- that is
    # share/plasma/shells/org.kde.plasma.desktop here. Read from the call
    # rather than written out, so moving the package shows up as a failure.
    call = re.search(r"plasma_install_package\(desktoppackage\s+(\S+)\s+(\S+)",
                     (plasma_desktop / "CMakeLists.txt").read_text())
    assert call, "plasma_install_package(desktoppackage ...) is gone; where does layout.js land?"
    component, root = call.group(1), call.group(2)
    installed = f"usr/share/plasma/{root}/{component}/contents/layout.js"

    takers = []
    for install in sorted((plasma_desktop / "debian").glob("*.install")):
        for line in install.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if fnmatch(installed, line) or fnmatch(installed, line.rstrip("/") + "/*"):
                takers.append(install.name.removesuffix(".install"))
                break

    declaring = [p["Package"] for p in _paragraphs((plasma_desktop / "debian/control").read_text())
                 if LAYOUT_PROVIDES in p.get("Provides", "")]
    assert takers, f"no debian/*.install takes {installed}: it is built and never packaged"
    assert takers == declaring, (
        f"{installed} is shipped by {takers} but {LAYOUT_PROVIDES} is declared "
        f"by {declaring}. A dependency on that name would then be satisfied by "
        "a package that does not carry the layout -- the green that proves "
        "nothing this whole declaration exists to avoid")
