"""One copy of the two things every source-reading test here needs.

A test that reads the *result* of the series has to apply it first, and
three files were about to carry the same twelve lines. The series is
applied in order, to a copy: each patch must apply to what the ones before
it left, which is a different question from whether it applies on its own
to a pristine tree.

    ./fetch-sources.sh && pytest tests/
"""
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

TOP = Path(__file__).resolve().parent.parent
PATCHES = TOP / "patches"
COMPONENTS = TOP / "components"
# NOT inside the repository: /srv is a virtiofs share and a file written
# there from the build VM is born root:root, while the services that
# read /srv run as uid 1000. test_build_guards.py asserts nothing lands in
# work/ or out/ for exactly that reason, and 196 MB of sources there would
# make these two tests contradict each other.
_cache = os.environ.get("XDG_CACHE_HOME") or (
    os.path.join(os.environ["HOME"], ".cache") if os.environ.get("HOME")
    else "/var/tmp/raye-src")
DEFAULT_SRC = Path(_cache) / "raye" / "desktop-src"

def components():
    """The source packages and the version each series was written for."""
    out = {}
    for line in COMPONENTS.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, version = line.split()
        out[name] = version
    return out


HOW = ("no Ubuntu source. ./fetch-sources.sh gets it without building"
       " anything (--help); or point RAYE_DESKTOP_SRC at a directory of"
       " extracted sources")


def source_dir():
    """Where the sources are: RAYE_DESKTOP_SRC, or work/src, where
    ./fetch-sources.sh puts them (~/.cache/raye/desktop-src) -- so
    fetching once is enough and every later run, iso/tools/raye-tests
    included, finds them by itself.

    ⚠️ work/src counts only when it holds a tree for EVERY component. A
    directory with one of the two would otherwise be taken for both, and
    the test that needed the other would fail somewhere else entirely."""
    env = os.environ.get("RAYE_DESKTOP_SRC")
    if env:
        return env
    if DEFAULT_SRC.is_dir() and all(
            any(DEFAULT_SRC.glob(name + "-*")) for name in components()):
        return str(DEFAULT_SRC)
    return None


SRC = source_dir()

needs_source = pytest.mark.skipif(not SRC, reason=HOW)


def series(component):
    return sorted((PATCHES / component).glob("*.patch"))


@pytest.fixture(scope="session")
def patched():
    """patched("plasma-workspace") -> that source with its whole series applied.

    Session-scoped and cached: applying a series copies a source tree, and
    plasma-workspace's is 190 MB.
    """
    work = Path(tempfile.mkdtemp(prefix="raye-desktop-"))
    done = {}

    def apply_series(component):
        if component in done:
            return done[component]
        trees = [d for d in Path(SRC).iterdir() if d.is_dir() and d.name.startswith(component)]
        assert trees, f"no extracted {component} source under {SRC}"
        tree = work / component
        shutil.copytree(sorted(trees)[0], tree, symlinks=True)
        for patch in series(component):
            ran = subprocess.run(["patch", "-p1", "--silent", "-i", str(patch)],
                                 cwd=tree, capture_output=True, text=True)
            assert ran.returncode == 0, f"{patch.name} does not apply:\n{ran.stdout}{ran.stderr}"
        done[component] = tree
        return tree

    yield apply_series
    shutil.rmtree(work, ignore_errors=True)
