"""Nothing of the session connects to X11 at sign-in on Wayland, so KWin
starts Xwayland only for an X11 program (plasma-workspace/0005).

A rebase that brings back one of the three connections builds and runs
fine and silently costs Xwayland at every sign-in, so the source is read.

    ./fetch-sources.sh && pytest tests/
"""
import re

import pytest

from conftest import needs_source

pytestmark = needs_source


@pytest.fixture
def tree(patched):
    return patched("plasma-workspace")


def body(text, start, end_marker="\n}\n"):
    i = text.index(start)
    return text[i:text.index(end_marker, i)]


def test_ksmserver_does_not_force_xcb_on_wayland(tree):
    main = (tree / "ksmserver/main.cpp").read_text()
    assert 'qputenv("QT_QPA_PLATFORM", QByteArrayView("xcb"));' not in main
    assert 'onWayland ? QByteArrayView("minimal") : QByteArrayView("xcb")' in main
    # the X11-only parts are skipped instead of crashing without a display
    assert re.search(r"if \(KWindowSystem::isPlatformX11\(\)\) \{\s*kde_running\.emplace", main)


def test_legacy_save_only_on_x11(tree):
    logout = (tree / "ksmserver/logout.cpp").read_text()
    calls = re.findall(r"(.*)\n\s*performLegacySessionSave\(\);", logout)
    assert len(calls) == 2
    assert all("isPlatformX11" in line for line in calls), calls


def test_appmenu_connects_only_for_an_x11_window(tree):
    text = (tree / "appmenu/appmenu.cpp").read_text()
    constructor = body(text, "AppMenuModule::AppMenuModule(")
    assert "xcb_connect" not in constructor
    assert "xcb_connect" in body(text, "void AppMenuModule::slotWindowRegistered(")


def test_x_resources_wait_for_xwayland(tree):
    krdb = body((tree / "kcms/krdb/krdb.cpp").read_text(), "void runRdb(")
    assert "const bool haveX = xServerUp();" in krdb
    assert "haveX ? xcb_connect(nullptr, nullptr) : nullptr" in krdb
    assert re.search(r"if \(haveX\) \{\s*proc\.execute\(\);", krdb)
    fonts = (tree / "kcms/fonts/fontinit.cpp").read_text()
    assert "!xServerUp()" in fonts
