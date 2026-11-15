"""build.sh refuses the two shortcuts that look harmless and are not.

    python3 -m pytest -q tests/test_build_guards.py

🚨 Both guards were written after the mistake, on 2026-11-06, and both
mistakes were mine.

1. -flto=N to bound memory. Ubuntu's flags carry `-flto=auto
   -ffat-lto-objects`, and with no make jobserver -- CMake's generated
   recipes do not get one -- every link forks nproc ltrans processes. On a
   28-core VM with no swap that gets lto1 killed, so bounding it looks
   obvious. Appending `-flto=1` built plasma-workspace and then FAILED in
   dh_makeshlibs: libtaskmanager6 had lost symbols its shipped .symbols
   file lists, among them

       _ZTVN11TaskManager23AbstractTasksModelIfaceE@Base

   the vtable of an abstract class, plus shared_ptr template
   instantiations. One LTO partition lets GCC see the whole library and
   drop what it believes unused, so -flto=N changes the ABI SURFACE. dpkg
   is right to refuse. The ABI-neutral bound is JOBS.

   ⚠️ DPKG_GENSYMBOLS_CHECK_LEVEL=0 turns that refusal into a warning --
   it hides the ABI change rather than undoing it, and is never the answer.

2. A component name that is not in ./components. `./build.sh
   --aucun-composant` used to print "Done" and exit 0 having built nothing:
   the same shape as every other defect this tree has paid for, a command
   that succeeds without doing the work. A typo in a release script would
   produce an image carrying the archive's desktop with nothing to say so.

⚠️ These run build.sh for real, and both refusals happen BEFORE it touches
apt or the network, which is what makes them cheap to check. They are not
asserted by reading build.sh for a string: a comment mentioning -flto would
satisfy that, and the check would be green with the guard deleted.
"""
import os
import shutil
import subprocess
import tempfile

import pytest

from conftest import TOP, components

BUILD = TOP / "build.sh"
FLAG_VARS = [
    "DEB_CFLAGS_APPEND",
    "DEB_CXXFLAGS_APPEND",
    "DEB_LDFLAGS_APPEND",
    "DEB_CFLAGS_SET",
    "DEB_CXXFLAGS_SET",
    "DEB_LDFLAGS_SET",
]


def run(args=(), env_extra=None, cwd=None, timeout=20):
    env = dict(os.environ)
    env.pop("DEB_BUILD_OPTIONS", None)
    for var in FLAG_VARS:
        env.pop(var, None)
    # WORK out of the tree. build.sh unpacks sources under ./work by default,
    # and `test_every_real_component_is_accepted` runs it FOR REAL with a real
    # component name: before this line, every run of this file left ~134 MB of
    # apt sources in the repository, owned by root, because a file created in
    # /srv from this machine is born root:root and the services that read /srv
    # run as uid 1000. A test that litters the tree it checks is a defect of the
    # test. build.sh takes WORK=dir exactly for this.
    sandbox = os.path.join(tempfile.gettempdir(), f"raye-build-guards-{os.getpid()}")
    env["WORK"] = os.path.join(sandbox, "work")
    env["OUT"] = os.path.join(sandbox, "out")
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        ["sh", str(BUILD), *args],
        capture_output=True, text=True, env=env, timeout=timeout,
        cwd=str(cwd) if cwd else None,
    )


needs_root = pytest.mark.skipif(
    os.geteuid() != 0,
    reason="build.sh refuses to run as a normal user before it reaches these guards",
)


# ------------------------------------------------------- the -flto refusal
@needs_root
@pytest.mark.parametrize("var", FLAG_VARS)
@pytest.mark.parametrize("value", ["-flto=1", "-O2 -flto=4", "-flto-partition=one"])
def test_an_lto_override_is_refused(var, value):
    done = run(["plasma-desktop"], {var: value})
    assert done.returncode != 0, (
        f"{var}={value!r} was accepted. Overriding Ubuntu's -flto=auto changes "
        "which symbols the libraries export, and dh_makeshlibs then fails on "
        "the shipped .symbols file -- measured 2026-11-06 on libtaskmanager6."
    )
    assert var in done.stderr, f"the refusal does not name {var}: {done.stderr!r}"
    # the message has to hand over the bound that IS safe, or the next person
    # reaches for DPKG_GENSYMBOLS_CHECK_LEVEL=0 instead
    assert "JOBS" in done.stderr, (
        "the refusal does not say what to do instead; without JOBS named, the "
        f"obvious next move is to silence dpkg: {done.stderr!r}"
    )


@needs_root
def test_a_flag_without_lto_is_let_through():
    """The guard must not refuse every flag: it would be unusable and get removed."""
    done = run(["plasma-desktop"], {"DEB_CXXFLAGS_APPEND": "-O2 -g"})
    assert "-flto" not in done.stderr, (
        f"a flag with no -flto in it was refused as one: {done.stderr!r}"
    )


# -------------------------------------------- the unknown-component refusal
@needs_root
def test_an_unknown_component_is_refused():
    done = run(["--aucun-composant"])
    assert done.returncode != 0, (
        "an unknown component name built nothing and succeeded. That is the "
        "defect this guard exists for: a typo in a release script would make "
        "an image with the archive's desktop in it, silently."
    )
    assert "not a component" in done.stderr


@needs_root
def test_the_refusal_lists_the_real_components():
    """Naming them is what makes the message usable, and pins them to the file."""
    done = run(["--aucun-composant"])
    for name in components():
        assert name in done.stderr, (
            f"{name} is in ./components but the refusal does not list it"
        )


@needs_root
@pytest.mark.parametrize("name", list(components()))
def test_every_real_component_is_accepted(name):
    """⚠️ The half that catches a broken guard rather than a missing one.

    The first version of the check built its list with newlines between the
    names, so `case " $known " in *" <name> "*)` matched nothing and EVERY
    component -- including a correct one -- was refused. A test that only
    tried a bad name would have been green.
    """
    done = run([name], timeout=25)
    assert "not a component" not in done.stderr, (
        f"{name} is in ./components and build.sh refused it: {done.stderr!r}"
    )


@needs_root
def test_an_empty_components_file_is_not_a_silent_success(tmp_path):
    """A components file that is all comments must fail, not print Done."""
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "build.sh").write_text(BUILD.read_text())
    (tree / "components").write_text("# nothing here\n\n")
    (tree / "patches").mkdir()
    done = subprocess.run(
        ["sh", str(tree / "build.sh")],
        capture_output=True, text=True, timeout=20,
        env={k: v for k, v in os.environ.items() if k not in FLAG_VARS},
    )
    assert done.returncode != 0, (
        "an empty components file printed Done and exited 0: nothing was built "
        f"and nothing said so. stdout={done.stdout!r}"
    )
    assert "names no component" in done.stderr


LITTER = ("work", "out")


@pytest.fixture(scope="module", autouse=True)
def _no_litter():
    """Whatever build.sh unpacked goes away, and the tree is checked after.

    ⚠️ The check is `work` and `out` in the REPOSITORY, not in WORK: the point
    is that nothing landed where the services read.

    🚨 And it compares BEFORE with AFTER. Asserting that `work/` simply does
    not exist cannot tell what build.sh created from what was already there:
    anything that put a work/ in the tree failed this fixture, at teardown,
    with build.sh's name on the message -- a defect reported against the
    wrong thing is worse than none.
    """
    before = {name for name in LITTER if (TOP / name).exists()}
    yield
    shutil.rmtree(
        os.path.join(tempfile.gettempdir(), f"raye-build-guards-{os.getpid()}"),
        ignore_errors=True,
    )
    new = sorted(str(TOP / name) for name in LITTER
                 if (TOP / name).exists() and name not in before)
    assert not new, (
        f"running build.sh created {new} in the repository. Files created in "
        "/srv from this machine are born root:root and the services that read "
        "/srv run as uid 1000."
    )
