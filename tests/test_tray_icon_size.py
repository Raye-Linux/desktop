"""The notification area's icon size, read out of the result of the series.

The owner asked for a Windows 11 notification area: small icons, one row.
`patches/plasma-workspace/0003` draws them at Kirigami's iconSizes.small
instead of iconSizes.smallMedium, and takes the row divisor apart from the
icon size so that smaller icons do not quietly become two rows.

🚨 The arithmetic is the whole point of this file, so it is EXECUTED and not
re-written here. Asserting `floor(48 / 26) == 1` in Python would be a second
implementation of the thing being tested -- the shape this tree has already
paid for twice, a bench that compares two ways of reading and calls it
parity. So the real RayeTrayMetrics.qml out of the patched source is loaded
by qml6 against the real Kirigami, and its answers are read back.

⚠️ And the numbers are asserted as RELATIONS, never as literals. Kirigami's
icon sizes are multiplied by IconSizes::iconScaleFactor, which grows with the
font: a test pinning iconSize == 16 would pass on this machine and fail on a
larger font, for no defect. `rowsFor(48, n) == 1` survives any scale factor,
because the factor only ever makes the row thicker.

    ./fetch-sources.sh && pytest tests/
"""
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from conftest import needs_source

pytestmark = needs_source

APPLET = "applets/systemtray"
METRICS = APPLET + "/qml/RayeTrayMetrics.qml"


@pytest.fixture(scope="module")
def plasma_workspace(patched):
    return patched("plasma-workspace")


@pytest.fixture(scope="module")
def main_qml(plasma_workspace):
    return (plasma_workspace / APPLET / "qml/main.qml").read_text()


# ------------------------------------------------------------------ the text
#
# Three properties the text can answer on its own, and each is a thing that
# breaks silently rather than loudly.


def test_the_metrics_file_is_there(plasma_workspace):
    assert (plasma_workspace / METRICS).is_file(), (
        "RayeTrayMetrics.qml is gone from the applet: a rebase dropped the "
        "file the icon size lives in")


def test_the_metrics_file_is_compiled_into_the_applet(plasma_workspace):
    # Not housekeeping. plasma_add_applet(QML_SOURCES ...) lists the QML
    # files explicitly and compiles them into a module; a file missing from
    # that list does not exist at runtime, the component fails to resolve,
    # and the whole applet fails to load. That is only visible in a session,
    # which is exactly why it is asserted here.
    cmake = (plasma_workspace / APPLET / "CMakeLists.txt").read_text()
    sources = re.search(r"plasma_add_applet\((.*?)\n\)", cmake, re.S)
    assert sources, "plasma_add_applet() moved; this test no longer reads it"
    assert "qml/RayeTrayMetrics.qml" in sources.group(1), (
        "RayeTrayMetrics.qml is not in plasma_add_applet(QML_SOURCES): it "
        "would not be compiled into the applet's QML module, and the applet "
        "would not load at all")


def test_the_icon_size_is_not_the_row_divisor(main_qml):
    # The regression this patch exists to prevent, caught in the text as well
    # as in the arithmetic below: the row count must not be derived from the
    # icon size. With Raye's 16 px icon as the divisor, the 48 px panel Raye
    # ships gets two rows of tray icons.
    rows = re.search(r"readonly property int rowsOrColumns:(.*)", main_qml)
    assert rows, "rowsOrColumns is gone from main.qml"
    assert "smallIconSize" not in rows.group(1), (
        "rowsOrColumns divides by smallIconSize again: smaller icons now "
        "mean more rows, which is the bug patch 0003 was written around")


def test_scaling_to_the_panel_still_wins(main_qml):
    # The user's own escape hatch. This patch changes the CAPPED size only;
    # "Panel icon size: Scale with Panel height" and touch mode must still
    # take the size from the panel's thickness, or the patch has quietly
    # removed a setting instead of changing a default.
    auto = re.search(r"readonly property bool autoSize:(.*)", main_qml)
    assert auto, "autoSize is gone from main.qml"
    assert "scaleIconsToFit" in auto.group(1) and "tabletMode" in auto.group(1)
    assert "autoSize ?" in main_qml, "the auto-scaling branch is gone"


def test_the_label_in_main_xml_says_the_size_the_code_uses(plasma_workspace):
    # main.xml is the only place in the source that writes the cap down. It
    # said "capped at the smallMedium size (22px)"; a patch that changes the
    # code and leaves the sentence makes the source state something false
    # about itself, next to the code it describes.
    xml = (plasma_workspace / APPLET / "main.xml").read_text()
    assert "smallMedium size (22px)" not in xml, (
        "main.xml still says tray icons are capped at smallMedium (22px), "
        "which patch 0003 made untrue")
    assert "small size (16px)" in xml, (
        "main.xml no longer says what the cap is; the one written record of "
        "it in the source is gone")


# ------------------------------------------- the arithmetic, actually run

MARK = "RAYE-TRAY"

PROBE = """
import QtQuick
import org.kde.kirigami as Kirigami

Item {
    RayeTrayMetrics { id: m }

    Component.onCompleted: {
        // a panel exactly two icons thick: one row if the divisor is the row
        // thickness, two if somebody made it the icon size again
        const trap = 2 * (m.iconSize + Kirigami.Units.smallSpacing);
        console.log("%s"
            + " iconSize=" + m.iconSize
            + " small=" + Kirigami.Units.iconSizes.small
            + " smallMedium=" + Kirigami.Units.iconSizes.smallMedium
            + " rowThickness=" + m.rowThickness
            + " rows48=" + m.rowsFor(48, 5)
            + " rowsOne=" + m.rowsFor(m.rowThickness, 5)
            + " rowsTwo=" + m.rowsFor(2 * m.rowThickness, 5)
            + " rowsTrap=" + m.rowsFor(trap, 5)
            + " rowsNoIcons=" + m.rowsFor(2 * m.rowThickness, 0));
        Qt.exit(0);
    }
}
""" % MARK


@pytest.fixture(scope="module")
def measured(plasma_workspace):
    """What the real RayeTrayMetrics.qml answers, run against real Kirigami.

    Skipped only when there is no QML runtime at all -- never when one runs
    and says something unexpected. A guard that turned a wrong answer into a
    skip would be worse than no guard.
    """
    qml = shutil.which("qml6") or shutil.which("qml")
    if not qml:
        pytest.skip("no qml6: install qt6-declarative-dev-tools to run the"
                    " tray arithmetic against the real Kirigami")

    source = plasma_workspace / METRICS
    assert source.is_file(), (
        f"{METRICS} is not in the patched source, so there is no arithmetic "
        "to run: patches/plasma-workspace/0003 is missing or no longer "
        "creates the file")

    work = Path(tempfile.mkdtemp(prefix="raye-tray-"))
    try:
        # the production file itself, beside a probe that reads it: a
        # component in the same directory resolves by its file name
        shutil.copy(source, work / "RayeTrayMetrics.qml")
        (work / "probe.qml").write_text(PROBE)
        env = dict(os.environ, QT_QPA_PLATFORM="offscreen")
        ran = subprocess.run([qml, str(work / "probe.qml")], cwd=work, env=env,
                             capture_output=True, text=True, timeout=120)
        text = ran.stdout + ran.stderr
        if "org.kde.kirigami" in text and "is not installed" in text:
            pytest.skip("Kirigami's QML module is not installed")
        line = next((l for l in text.splitlines() if MARK in l), None)
        assert line, (
            "RayeTrayMetrics.qml did not load. That is a failure, not a "
            f"missing tool: qml6 exited {ran.returncode} and said:\n{text}")
        return {k: int(v) for k, v in re.findall(r"(\w+)=(-?\d+)", line)}
    finally:
        shutil.rmtree(work, ignore_errors=True)


def test_the_tray_icon_is_kirigamis_small_size(measured):
    assert measured["iconSize"] == measured["small"], (
        "the tray icon is no longer Kirigami's small size")
    assert measured["small"] < measured["smallMedium"], (
        "Kirigami's small is not smaller than its smallMedium: the premise "
        "of this patch -- that it makes the icons smaller -- is gone")


def test_a_row_is_thicker_than_an_icon(measured):
    assert measured["iconSize"] < measured["rowThickness"], (
        "an icon is as thick as the row it sits in, so the icons fill the "
        "panel edge to edge; they are meant to be small inside it")


def test_rayes_own_48_px_panel_keeps_one_row(measured):
    # The number that decides whether this looks finished. 48 is the height
    # layout.js gives the panel in patches/plasma-desktop/0003, and it is a
    # literal there, so it is a literal here.
    assert measured["rows48"] == 1, (
        "the notification area is two rows deep on the 48 px panel Raye "
        "ships. That is what drawing the icons smaller does if the row "
        "count is derived from the icon size -- see patch 0003")


def test_a_panel_two_icons_thick_is_still_one_row(measured):
    # The same trap, free of any one panel height: a panel just thick enough
    # for two 16 px icons must still hold a single row.
    assert measured["rowsTrap"] == 1, (
        "a panel two icon-heights thick now holds two rows: the divisor has "
        "become the icon size again")


def test_the_rows_are_still_counted_the_way_plasma_counts_them(measured):
    # Upstream's intent, said scale-free: one row per rowThickness of panel.
    # Its own comment puts it at "2 rows/columns on a 56px panel", which is
    # this with smallMedium = 22 and smallSpacing = 4.
    assert measured["rowsOne"] == 1
    assert measured["rowsTwo"] == 2, (
        "a panel twice a row thick no longer holds two rows: the patch has "
        "changed how Plasma lays the tray out, not just how big an icon is")


def test_an_empty_tray_is_one_row_and_not_none(measured):
    # Math.max(1, ...) in the formula. A zero here would divide by it later.
    assert measured["rowsNoIcons"] == 1
