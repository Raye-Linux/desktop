"""That the package build really runs the Raye tests.

🚨 This file exists because the build said nothing three times in a row and
each silence looked like a pass. Both components' packaging configures with
-DBUILD_TESTING=OFF and empties dh_auto_test, and on top of that:

  * include(CTest) only calls enable_testing() when BUILD_TESTING is on, so
    add_test() registers nothing without a call by hand;
  * ctest exits 0 when it finds no test to run.

Put together, a series whose tests stop being registered builds green for
ever. These read the patched tree for each of the pieces that stops that
happening again.

⚠️ Every check here runs for *every* component. It used to read
plasma-desktop only, and plasma-workspace joined the series with the same
three traps and its own copy of the scaffolding: a check that covers one
component is a silence waiting for the second.
"""
import re

import pytest

from conftest import components, needs_source

pytestmark = needs_source

COMPONENTS = list(components())


@pytest.fixture(params=COMPONENTS, ids=COMPONENTS)
def tree(request, patched):
    return patched(request.param)


@pytest.fixture
def rules(tree):
    return (tree / "debian/rules").read_text()


@pytest.fixture
def cmakelists(tree):
    return (tree / "CMakeLists.txt").read_text()


def test_the_build_turns_the_raye_tests_on(rules):
    assert "-DRAYE_TESTING=ON" in rules, (
        "the build does not turn RAYE_TESTING on, so the test directory is "
        "never even added")


def test_the_tests_are_registered_at_all(cmakelists):
    # enable_testing() has to be called where RAYE_TESTING is honoured;
    # include(CTest) will not do it with BUILD_TESTING off
    block = re.search(r"if\(RAYE_TESTING\)(.*?)endif\(\)", cmakelists, re.S)
    assert block, "nothing in CMakeLists honours RAYE_TESTING on its own"
    assert "enable_testing()" in block.group(1), (
        "enable_testing() is not called, so add_test() registers nothing and "
        "ctest will report that it found no test -- and exit 0")


def test_every_raye_test_is_registered(tree):
    # a test built but never registered is a test that does not exist, and
    # --no-tests=error cannot see the difference once one other test is there
    written = sorted(p.name for p in tree.rglob("tst_raye*.cpp"))
    assert written, "this component's series has no Raye test at all"
    registered = set()
    for cml in tree.rglob("CMakeLists.txt"):
        for name in re.findall(r"add_test\(NAME (raye\w+)", cml.read_text()):
            registered.add(name)
    for source in written:
        expected = source.removeprefix("tst_").removesuffix(".cpp")
        assert expected in registered, (
            f"{source} is in the series but add_test(NAME {expected} ...) is "
            f"nowhere: it would be built and never run. Registered: "
            f"{sorted(registered)}")


def test_a_build_that_runs_no_test_fails(rules):
    assert "--no-tests=error" in rules, (
        "ctest exits 0 when it finds nothing to run: without --no-tests=error "
        "a series whose tests stopped being registered builds green for ever")


def test_only_rayes_own_tests_run(rules):
    # upstream's are left exactly as Ubuntu had them: one of plasma-desktop's
    # never ends, and plasma-workspace's want a Wayland compositor
    assert "-DBUILD_TESTING=OFF" in rules
    assert re.search(r"ctest .*-R '\^raye'", rules, re.S), (
        "the build does not restrict ctest to Raye's tests")


def test_nocheck_still_skips_them(rules):
    # dh calls an override even under nocheck, so the skip has to be written
    assert "nocheck" in rules and "ifeq" in rules, (
        "DEB_BUILD_OPTIONS=nocheck would not skip the Raye tests")


def test_every_raye_test_directory_can_find_qt_test(tree):
    # with BUILD_TESTING off nothing else in either tree pulls Qt6::Test in,
    # and the configure step then fails rather than skipping the tests --
    # which is the good failure, but only if the find_package is there to
    # make it pass
    directories = sorted({p.parent for p in tree.rglob("tst_raye*.cpp")})
    assert directories, "this component's series has no Raye test at all"
    for directory in directories:
        text = (directory / "CMakeLists.txt").read_text()
        assert "find_package(Qt6" in text and "Test" in text, (
            f"{directory.relative_to(tree)}/CMakeLists.txt does not ask for "
            "Qt6::Test, so its tests do not configure with BUILD_TESTING off")


def test_a_raye_test_directory_is_reached_with_build_testing_off(tree):
    # the directory is added under `BUILD_TESTING OR RAYE_TESTING`: added under
    # BUILD_TESTING alone it would never be reached by this packaging, and the
    # test would silently not exist.
    #
    # The path in add_subdirectory() is relative to the CMakeLists.txt that
    # holds it, and the two components spell it differently -- plasma-desktop
    # adds desktoppackage/autotests from the top level, plasma-workspace adds
    # raye-autotests from shell/. Matching on the last component of the name
    # would pass for one and fail for the other.
    directories = sorted({p.parent for p in tree.rglob("tst_raye*.cpp")})
    assert directories, "this component's series has no Raye test at all"
    for directory in directories:
        reached = False
        for cml in tree.rglob("CMakeLists.txt"):
            try:
                relative = directory.relative_to(cml.parent)
            except ValueError:
                continue
            for _condition, body in re.findall(r"if\(([^)]*RAYE_TESTING[^)]*)\)(.*?)endif\(\)",
                                              cml.read_text(), re.S):
                if f"add_subdirectory({relative.as_posix()})" in body:
                    reached = True
        assert reached, (
            f"no `if(... RAYE_TESTING ...)` adds {directory.relative_to(tree)}, "
            "so with BUILD_TESTING off its tests are never built")
