"""The Raye revision moves when the series does.

A package that changes without a new version is not an update: apt and
Raye Update see nothing to install, and a machine that already has
+raye1 keeps it. Worse, the package pins file times to its changelog
date, and plasmashell keys its compiled QML cache on those times, so the
old code goes on running even where the new files did land.

revisions holds one line per revision: the number and the sha256 of the
whole series it was built from. Changing a patch without adding a line
(and raising raye_revision in build.sh) fails here.

    pytest tests/test_revision.py
"""
import hashlib
import re

from conftest import TOP, components, series

REVISIONS = TOP / "revisions"


def series_sum():
    """One sum for every patch of every component, names included, so a
    rename or a patch moved to the other component counts too."""
    h = hashlib.sha256()
    for component in sorted(components()):
        for patch in series(component):
            h.update(f"{component}/{patch.name}\n".encode())
            h.update(patch.read_bytes())
            h.update(b"\0")
    return h.hexdigest()


def recorded():
    out = []
    for line in REVISIONS.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        number, digest = line.split()
        out.append((int(number), digest))
    return out


def build_revision():
    m = re.search(r"^raye_revision=(\d+)$", (TOP / "build.sh").read_text(), re.M)
    assert m, "build.sh has no raye_revision=<n> line"
    return int(m.group(1))


def test_revisions_go_up():
    numbers = [n for n, _ in recorded()]
    assert numbers, "revisions is empty"
    assert numbers == sorted(set(numbers)), f"revisions must only go up: {numbers}"


def test_build_uses_the_last_revision():
    last, _ = recorded()[-1]
    assert build_revision() == last, (
        f"build.sh builds +raye{build_revision()}, revisions ends at {last}")


def test_the_series_has_not_moved_since_the_last_revision():
    last, digest = recorded()[-1]
    now = series_sum()
    assert digest == now, (
        f"the patch series changed since +raye{last} was recorded. Raise "
        f"raye_revision in build.sh and add to revisions:\n    {last + 1} {now}")
