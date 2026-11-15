"""What the desktop's shell calls itself, read out of the result of the series.

A file copy started from the desktop and every error the shell shows were
headed "Plasma Desktop Workspace" with the Plasma logo: the name and the icon
come from the shell's own .desktop file. `patches/plasma-workspace/0004` makes
that file say Raye, in every language.

    ./fetch-sources.sh && pytest tests/
"""
import re

from conftest import needs_source


@needs_source
def test_the_shell_is_called_raye_in_every_language(patched):
    tree = patched("plasma-workspace")
    entry = (tree / "shell/org.kde.plasmashell.desktop.cmake").read_text()
    names = re.findall(r"^Name(\[[^\]]+\])?=(.*)$", entry, re.M)
    assert names == [("", "Raye")], (
        "the file has its own translations: one left behind is the old name "
        f"in that language: {names[:3]}")
    assert re.search(r"^Icon=raye-eye$", entry, re.M)


@needs_source
def test_the_shell_tells_applications_its_name(patched):
    tree = patched("plasma-workspace")
    main = (tree / "shell/main.cpp").read_text()
    assert 'i18n("Plasma Shell")' not in main
    assert 'QStringLiteral("Raye")' in main
    # the plugin name stays: D-Bus, config files and the service use it
    assert 'KAboutData aboutData(QStringLiteral("plasmashell")' in main
