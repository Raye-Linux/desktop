"""What the desktop ends up shipping, once the series is applied.

The patches are read elsewhere; this reads the *result*. A rebase that
drops a line, or moves it into the wrong section, is the failure these
catch -- and the one a patch-text test cannot see.

Needs a source to apply the series to:

    ./fetch-sources.sh && pytest tests/
"""
import pytest

from conftest import needs_source

pytestmark = needs_source


@pytest.fixture(scope="module")
def plasma_desktop(patched):
    """A plasma-desktop source with the whole Raye series applied."""
    return patched("plasma-desktop")


def sections(text):
    """The shell package's defaults, as {section: {key: value}}."""
    out, current = {}, None
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("["):
            current = line
            out.setdefault(current, {})
        elif "=" in line and current:
            key, _, value = line.partition("=")
            out[current][key] = value
    return out


@pytest.fixture(scope="module")
def shell_defaults(plasma_desktop):
    return sections((plasma_desktop / "desktoppackage/contents/defaults").read_text())


WHEEL = "wheel:Vertical;ControlModifier"
DESKTOP = "[Desktop][ContainmentActions]"
PANEL = "[Panel][ContainmentActions]"


def test_the_desktop_resizes_its_icons_on_ctrl_wheel(shell_defaults):
    assert shell_defaults[DESKTOP].get(WHEEL) == "org.raye.desktopmenu"


def test_the_desktop_keeps_the_bindings_it_already_had(shell_defaults):
    # libplasma reads this section as a whole. Dropping a line here does not
    # fall back to anything: it takes the gesture away from every account that
    # has not overridden it.
    assert shell_defaults[DESKTOP].get("RightButton;NoModifier") == "org.kde.contextmenu", \
        "the desktop's right click menu is gone"
    assert shell_defaults[DESKTOP].get("MiddleButton;NoModifier") == "org.kde.paste", \
        "the desktop's middle click paste is gone"


def test_the_taskbar_is_not_given_the_desktop_gesture(shell_defaults):
    # Ctrl + wheel on a panel has nothing to resize, and a binding there would
    # only take the gesture away from whatever the panel does with the wheel.
    assert WHEEL not in shell_defaults.get(PANEL, {})
