"""plasmashell hands freed heap back to the system (plasma-workspace/0006).

The holes it leaves in its heap are counted as its memory, about 30 MB once
the desktop has settled. A rebase that drops the timer builds and runs fine
and quietly costs that memory again, so the source is read.

    ./fetch-sources.sh && pytest tests/
"""
import re

import pytest

from conftest import needs_source

pytestmark = needs_source


@pytest.fixture
def tree(patched):
    return patched("plasma-workspace")


def test_main_starts_the_trim(tree):
    main = (tree / "shell/main.cpp").read_text()
    assert '#include "heaptrim.h"' in main
    # after corona.init(), before the event loop: the desktop is up by then
    tail = main[main.index("corona.init();"):main.index("return app.exec();")]
    assert re.search(r"HeapTrim \w+\(60s, 10min\);", tail), tail


def test_the_trim_uses_malloc_trim(tree):
    header = (tree / "shell/heaptrim.h").read_text()
    assert "malloc_trim(0);" in header
    # a coarse timer may share a wakeup; a very coarse one rounds an interval
    # under a second down to zero and then never stops firing
    assert "setTimerType(Qt::CoarseTimer)" in header


def test_the_trim_has_a_raye_test(tree):
    cml = (tree / "shell/raye-autotests/CMakeLists.txt").read_text()
    assert "add_test(NAME rayeheaptrim" in cml
    assert (tree / "shell/raye-autotests/tst_rayeheaptrim.cpp").exists()
