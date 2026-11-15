"""The session's XDG menu prefix, which decides whose application menu it reads.

🚨 Why this file exists, measured on 2026-11-06 against
plasma-workspace 6.6.6-0ubuntu0.1.

Raye ships nine application categories (theme/shell/menus/raye-applications.menu)
and a three-line session environment script that exported
`XDG_MENU_PREFIX=raye-` so that KSycoca would read them. It could not work:

    startplasma-wayland.cpp:66   runEnvironmentScripts();   <- the script runs
    startplasma-wayland.cpp:72   setupPlasmaEnvironment();
    startplasma.cpp:410            qputenv("XDG_MENU_PREFIX", "plasma-");

and the same order in startplasma-x11.cpp (58, then 62). Every mechanism
outside the source -- that script, a profile snippet, the login manager,
systemd's own environment -- has already run by the time line 410 overwrites
the value unconditionally. `importSystemdEnvrionment()`, which runs after,
skips every name starting with XDG_ (`isSessionVariable`), so it cannot put it
back either.

So the categories were installed, correct and never read: the same shape as
the layout of plasma-workspace/0001 and the containment binding of
plasma-desktop/0002, and the third time this tree has paid for it.

⚠️ Division of labour with the Raye test in the package build
(startkde/raye-autotests/tst_rayemenuprefix.cpp): that one checks what the
helper *does*, this one checks that the helper is *called*, where it is called,
and that the premise of the patch's Reason still holds. A C++ test cannot do
the last two without linking and running setupPlasmaEnvironment(), which
writes in the account's configuration directory and talks to D-Bus.

    ./fetch-sources.sh && pytest tests/
"""
import re

import pytest

from conftest import needs_source

pytestmark = needs_source

COMPONENT = "plasma-workspace"
# the one line this patch stands in for
UPSTREAM = 'qputenv("XDG_MENU_PREFIX", "plasma-")'
ENTRY_POINTS = ["startplasma-wayland.cpp", "startplasma-x11.cpp"]


@pytest.fixture
def startkde(patched):
    return patched(COMPONENT) / "startkde"


def function_body(text, name):
    """The body of a top-level function, from its brace to the one in column 1.

    The file is clang-formatted with the closing brace of a top-level
    definition in column 1, which is what makes this cheap and exact.
    """
    start = text.index(f"void {name}()")
    end = text.index("\n}\n", start)
    return text[start:end]


def test_the_session_does_not_force_upstreams_menu_prefix(startkde):
    text = (startkde / "startplasma.cpp").read_text()
    assert UPSTREAM not in text, (
        "startplasma still sets the menu prefix to Plasma's own, after every "
        "mechanism outside the source has run. Raye's application categories "
        "are installed and unreachable whenever that line is there")


def test_the_prefix_is_written_from_exactly_one_place(patched):
    """A rebase that re-added upstream's line beside Raye's would leave two
    writers of one variable, and whichever ran last would win in silence.

    ⚠️ What counts is an assignment, not a mention: the call site carries a
    comment naming the variable, and the Raye test sets it on purpose to
    stand in for what a session inherits. The first version of this test
    counted mentions and failed on both -- a test that cannot tell writing
    from talking about writing.
    """
    tree = patched(COMPONENT)
    writers = sorted(
        str(path.relative_to(tree))
        for path in list(tree.rglob("*.cpp")) + list(tree.rglob("*.h"))
        if 'qputenv("XDG_MENU_PREFIX"' in path.read_text(errors="ignore")
        and "raye-autotests" not in path.parts
    )
    assert writers == ["startkde/rayemenuprefix.h"], (
        "XDG_MENU_PREFIX is assigned from more than one place, or from a "
        f"place this test does not know: {writers}")


def test_the_prefix_is_rayes_and_keeps_its_trailing_dash(startkde):
    """The specification puts the prefix straight in front of the file name,
    so the '-' is part of the value. Without it KSycoca looks for
    rayeapplications.menu, finds nothing, and falls back without a word."""
    header = (startkde / "rayemenuprefix.h").read_text()
    assert 'QByteArrayLiteral("raye-")' in header, (
        "the prefix is not exactly \"raye-\", so it does not name "
        "raye-applications.menu, which is the file Raye installs")


def test_the_prefix_is_set_where_the_session_environment_is_set_up(startkde):
    """Not anywhere: in setupPlasmaEnvironment(), which is the function that
    runs after every outside mechanism and is the only place that can win."""
    text = (startkde / "startplasma.cpp").read_text()
    assert "#include \"rayemenuprefix.h\"" in text, (
        "startplasma.cpp does not include the Raye prefix header")
    body = function_body(text, "setupPlasmaEnvironment")
    assert "setRayeMenuPrefix()" in body, (
        "setupPlasmaEnvironment() does not set the Raye menu prefix. Setting "
        "it earlier than this function would be overwritten; setting it later "
        "is after the environment has been sent to D-Bus and systemd")


@pytest.mark.parametrize("entry", ENTRY_POINTS)
def test_the_environment_scripts_have_already_run_by_then(startkde, entry):
    """🚨 The premise of this patch's Reason, asserted rather than remembered.

    An environment script cannot set this variable *because* it is sourced
    before setupPlasmaEnvironment(). The day upstream reorders those two
    calls, the script would work again and this patch stops being the only
    way -- and this test says so instead of leaving a correction nobody can
    explain. It is the same shape as plasma-workspace/0001's case asserting
    that KPackage still falls back at all.
    """
    text = (startkde / entry).read_text()
    scripts = text.index("runEnvironmentScripts()")
    setup = text.index("setupPlasmaEnvironment()")
    assert scripts < setup, (
        f"{entry} now sources the environment scripts after the session "
        "environment is set up, so a script could set XDG_MENU_PREFIX again "
        "and this patch's reason no longer holds")


@pytest.mark.parametrize("entry", ENTRY_POINTS)
def test_nothing_resets_the_prefix_after_it_is_set(startkde, entry):
    """importSystemdEnvrionment() runs after setupPlasmaEnvironment() and
    could put an inherited value back. It does not: it skips every name
    starting with XDG_ (isSessionVariable). Checked, because that filter is
    upstream's and could change under us."""
    guard = (startkde / "startplasma.cpp").read_text()
    body = function_body(guard, "importSystemdEnvrionment")
    assert "isSessionVariable" in body, (
        "importSystemdEnvrionment() no longer filters session variables, so "
        "it may import an inherited XDG_MENU_PREFIX over the Raye one")
    filter_body = guard[guard.index("bool isSessionVariable"):]
    filter_body = filter_body[: filter_body.index("\n}\n")]
    assert 'startsWith("XDG_"' in filter_body, (
        "isSessionVariable no longer covers every XDG_ name, so an inherited "
        "XDG_MENU_PREFIX can come back after Raye's is set")
