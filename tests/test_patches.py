"""The Raye desktop series: what every patch must say, and must not do.

The point of this repository is that Raye's changes live in the desktop's
code. These tests are what keeps it that way: a patch that only moves a
setting, or that arrives without saying why it cannot live outside the
source, is the theme layer coming back in through the patch series.

The test that a patch still applies needs a source tree, so it is the
build that gates it (build.sh refuses a patch that does not apply, and a
source version the series was not written for). Point RAYE_DESKTOP_SRC at
an extracted source to run it here too:

    ./fetch-sources.sh && pytest tests/
"""
import os
import re
import subprocess
from pathlib import Path

import pytest

# what a component is, and what its series is, are defined once: conftest.py
from conftest import PATCHES, TOP, components, series


def every_patch():
    return [(c, p) for c in components() for p in series(c)]


def ids(pairs):
    return [f"{c}/{p.name}" for c, p in pairs]


ALL = every_patch()


def test_every_component_has_a_series():
    for component in components():
        assert (PATCHES / component).is_dir(), f"no patches/{component}"
        assert series(component), (
            f"{component} is in components but has no patch: building it would "
            "only shadow the archive's own package")


def test_every_series_belongs_to_a_component():
    known = set(components())
    for directory in sorted(d for d in PATCHES.iterdir() if d.is_dir()):
        assert directory.name in known, (
            f"patches/{directory.name} is not in components, so build.sh never "
            "builds it and nobody would notice it going stale")


def test_the_series_has_something_in_it():
    assert ALL, "no patch at all: nothing here is in the desktop's code yet"


@pytest.mark.parametrize("component,patch", ALL, ids=ids(ALL))
def test_a_patch_says_what_it_does(component, patch):
    text = patch.read_text()
    subject = re.search(r"^Subject: (.+)$", text, re.M)
    assert subject, f"{patch.name} has no Subject: line"
    assert len(subject.group(1)) > 20, "the Subject says too little to be read later"


@pytest.mark.parametrize("component,patch", ALL, ids=ids(ALL))
def test_a_patch_says_why_it_cannot_live_outside_the_source(component, patch):
    # The one rule that keeps this from becoming a theme layer again: a patch
    # carries the reason the change is impossible as a setting, a script or a
    # look-and-feel package. Without it, the series grows by habit.
    # the header is everything before the first diff
    header = patch.read_text().split("\n--- ")[0]
    reason = re.search(r"^Reason:(.*)", header, re.M | re.S)
    assert reason, (
        f"{patch.name} has no 'Reason:' paragraph. Say why this cannot be done "
        "from a config file, a script or a look-and-feel package -- if it can, "
        "it does not belong in the series.")
    assert len(reason.group(1).split()) >= 12, (
        f"{patch.name}: the reason is too short to be a reason")


@pytest.mark.parametrize("component,patch", ALL, ids=ids(ALL))
def test_a_patch_changes_code_not_only_packaging(component, patch):
    touched = re.findall(r"^\+\+\+ b/(\S+)", patch.read_text(), re.M)
    assert touched, f"{patch.name} changes no file"
    assert any(not f.startswith("debian/") for f in touched), (
        f"{patch.name} only changes debian/: that is packaging, and it belongs "
        "in the component's own packaging, not in the Raye series")


@pytest.mark.parametrize("component,patch", ALL, ids=ids(ALL))
def test_a_patch_does_not_ship_a_config_default_instead(component, patch):
    # Installing a file into /etc/xdg from inside the source is the theme
    # layer wearing a patch: a user's own file still wins over it, and a
    # reset still gives KDE's value. A default belongs in the code that
    # reads it.
    added = [l[1:] for l in patch.read_text().splitlines() if l.startswith("+")]
    for line in added:
        assert "/etc/xdg" not in line, (
            f"{patch.name} installs into /etc/xdg: a default put there is still "
            "a layer above the code. Put it where the code reads it.")
        assert "KDE_INSTALL_CONFDIR" not in line, (
            f"{patch.name} installs a config file through KDE_INSTALL_CONFDIR, "
            "which is /etc/xdg: see above.")


@pytest.mark.parametrize("component", list(components()), ids=list(components()))
def test_the_patches_of_a_component_are_numbered_without_a_gap(component):
    numbers = []
    for patch in series(component):
        head = re.match(r"^(\d{4})-", patch.name)
        assert head, f"{patch.name} does not start with a four-digit number"
        numbers.append(int(head.group(1)))
    assert numbers == list(range(1, len(numbers) + 1)), (
        f"{component}: the numbers are {numbers}; the order a patch is applied "
        "in is part of what it means, so it may not have holes or repeats")


from conftest import HOW, SRC


@pytest.mark.skipif(not SRC, reason=HOW)
@pytest.mark.parametrize("component", list(components()), ids=list(components()))
def test_the_series_applies_to_the_source_it_was_written_for(component):
    # The series is applied in order, to a copy, and each patch must apply to
    # what the ones before it left. Trying a patch on its own against a
    # pristine source is a different question, and the wrong one: a later
    # patch may well touch a file an earlier one creates.
    import shutil
    import tempfile

    trees = [d for d in Path(SRC).iterdir() if d.is_dir() and d.name.startswith(component)]
    assert trees, f"no extracted {component} source under {SRC}"
    work = Path(tempfile.mkdtemp(prefix="raye-desktop-series-"))
    try:
        tree = work / component
        shutil.copytree(trees[0], tree, symlinks=True)
        for patch in series(component):
            done = subprocess.run(["patch", "-p1", "--dry-run", "--silent", "-i", str(patch)],
                                  cwd=tree, capture_output=True, text=True)
            assert done.returncode == 0, (
                f"{patch.name} does not apply to the source the patches before it "
                f"left:\n{done.stdout}{done.stderr}")
            subprocess.run(["patch", "-p1", "--silent", "-i", str(patch)], cwd=tree, check=True)
    finally:
        shutil.rmtree(work, ignore_errors=True)


# ---------------------------------------------------------------- build.sh
#
# A Raye image ships ubuntu.sources with its deb-src groups "Enabled: no",
# because turned on they cost every machine 18 MiB of source indexes at every
# apt update (measured; Ubuntu's own ubuntu.sources does the same). So on a
# Raye machine, `apt-get source` failing is the NORMAL first failure of this
# build, and the message is the only thing standing between the next person
# and an afternoon in the wrong file. These two tests keep that pointer true.


def build_sh():
    return (TOP / "build.sh").read_text()


def test_the_source_failure_names_the_file_to_edit():
    """The message must name ubuntu.sources, not just ask a question."""
    message = build_sh()
    assert "no source for $source_package" in message, (
        "the apt-get source failure changed shape; this test and the message "
        "below it are now describing something that no longer exists"
    )
    i = message.index("no source for $source_package")
    text = message[i : i + 400]
    assert "ubuntu.sources" in text, (
        "the apt-get source failure does not name /etc/apt/sources.list.d/"
        "ubuntu.sources. On a Raye machine that file is where deb-src is "
        "turned off, and 'is deb-src enabled?' alone sends people to "
        "sources.list, which Raye does not use"
    )
    assert "Enabled: no" in text, (
        "the message does not show the Enabled: no -> yes edit, so it names "
        "the file without saying what to change in it"
    )


def test_the_components_are_the_versions_that_need_updates():
    """Every component pins a -0ubuntu0.1-style version, which lives in
    resolute-updates. If one ever pins a plain resolute version, the
    deb-src pointer above stops being the whole story and must be revisited."""
    for component in components():
        line = [
            l for l in (TOP / "components").read_text().splitlines()
            if l.strip() and not l.startswith("#") and l.split()[0] == component
        ]
        assert line, f"{component} vanished from components"
        version = line[0].split()[1]
        assert "ubuntu" in version, (
            f"{component} pins {version}, which does not look like an Ubuntu "
            "package version; the build's source lookup assumes it does"
        )
