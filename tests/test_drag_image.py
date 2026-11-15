"""What moving desktop icons looks like.

As on Windows: the icon stays at its place, dimmed, and a see-through copy
of the icon and its name follows the pointer; several icons go as a stack
with a count. `patches/plasma-desktop/0005` does it in the delegate, the
view and FolderModel. Read out of the result of the series, because those
are upstream's files and a rebase can quietly put the old behaviour back.
How the copy is drawn is tested in C++ (tst_rayedragghost, run by the
package build).

    ./fetch-sources.sh && pytest tests/test_drag_image.py
"""
import re

import pytest

from conftest import needs_source

pytestmark = needs_source

UI = "containments/desktop/package/contents/ui/"
FOLDER = "containments/desktop/plugins/folder/"


@pytest.fixture(scope="module")
def tree(patched):
    return patched("plasma-desktop")


@pytest.fixture(scope="module")
def delegate(tree):
    return (tree / UI / "FolderItemDelegate.qml").read_text()


@pytest.fixture(scope="module")
def update_drag_image(delegate):
    m = re.search(r"function updateDragImage\(\) \{(.*?)\n    \}\n", delegate, re.S)
    assert m, "updateDragImage() moved; this test no longer reads it"
    return m.group(1)


@pytest.fixture(scope="module")
def model(tree):
    return (tree / FOLDER / "foldermodel.cpp").read_text()


def loader_block(delegate):
    m = re.search(r"\n    Loader \{\n        id: loader\n(.*?)\n    \}\n", delegate, re.S)
    assert m, "the delegate's loader moved; this test no longer reads it"
    return m.group(1)


def test_dragged_icon_stays_loaded(delegate):
    assert re.search(r"leftBehind:\s*model\.blank && \(model\.dragged", delegate)
    assert re.search(r"active:\s*!main\.model\.blank \|\| main\.leftBehind", loader_block(delegate)), (
        "a dragged row unloads its delegate again: the icon vanishes from "
        "its place while it is moved")


def test_selection_frame_survives_a_row_going_blank(delegate):
    # the delegate now outlives a drag: when its row moves away the model
    # stops answering "selected" before the loader is switched off
    assert "pressed: main.model?.selected ?? false" in delegate


def test_dragged_icon_keeps_its_name(delegate):
    assert re.search(r"name:\s*model\.blank && !leftBehind \? \"\" : model\.display\b", delegate)


def test_dragged_icon_is_dimmed_until_it_lands(delegate):
    m = re.search(r"opacity:\s*main\.leftBehind && !main\.GridView\.view\.iconsLanded \? (0\.\d+) : 1",
                  loader_block(delegate))
    assert m, "the icon left at its place is not dimmed"
    assert 0.3 <= float(m.group(1)) <= 0.6


def test_view_says_when_icons_land(tree):
    view = (tree / UI / "FolderView.qml").read_text()
    assert "property bool iconsLanded: false" in view
    start = view.index("gridView.iconsLanded = false;")
    assert start < view.index("dir.dragSelected(mouse.x, mouse.y);", start)
    landed = view.index("gridView.iconsLanded = true;")
    assert landed < view.index("positioner.move(moves)", landed)


def test_cell_decides_where_it_lands(update_drag_image):
    # registered first and with the delegate's own rectangle, so the cursor
    # offset of every icon is upstream's, whatever the picture looks like
    first = update_drag_image.index("dir.addItemDragImage(")
    assert re.match(r"dir\.addItemDragImage\(row, main\.x \+ loader\.x, main\.y \+ loader\.y, loader\.width, loader\.height, null\)",
                    update_drag_image[first:])
    assert first < update_drag_image.index("grabToImage(")


def test_picture_is_icon_and_name(update_drag_image):
    assert re.search(r"\bicon\.grabToImage\(", update_drag_image)
    assert re.search(r"\btext\.grabToImage\(", update_drag_image)
    assert "dir.addItemDragGhost(row, iconRect, iconShot.image, textRect, textShot.image)" in update_drag_image
    icon = update_drag_image.index("icon.grabToImage(")
    whole = update_drag_image.index("loader.grabToImage(")
    assert icon < whole and "return;" in update_drag_image[icon:whole], (
        "the whole delegate is grabbed too, selection frame and hover button")


def test_model_has_a_dragged_role(tree, model):
    header = (tree / FOLDER / "foldermodel.h").read_text()
    assert re.search(r"\bDraggedRole,", header)
    assert 'roleNames[DraggedRole] = QByteArrayLiteral("dragged");' in model
    assert re.search(r"role == BlankRole \|\| role == DraggedRole\)\s*\{\s*return m_dragIndexes\.contains\(index\);", model)
    # both changes of the drag state tell the delegate
    assert model.count("{BlankRole, DraggedRole}") == 2
    assert "{BlankRole})" not in model


def test_model_draws_the_ghost(model):
    m = re.search(r"void FolderModel::addDragImage\(QDrag \*drag, int x, int y\)\n\{(.*?)\n\}\n", model, re.S)
    assert m
    body = m.group(1)
    assert "RayeDragGhost::compose(" in body
    assert "image->cursorOffset = cell.topLeft() - QPoint(x, y);" in body
    assert "const QRect cell = image->rect.translated(-scroll);" in body


def test_ghost_is_built_and_tested(tree):
    cmake = (tree / FOLDER / "CMakeLists.txt").read_text()
    assert re.search(r"^\s+rayedragghost\.cpp$", cmake, re.M)
    tests = (tree / FOLDER / "raye-autotests/CMakeLists.txt").read_text()
    assert "add_test(NAME rayedragghost COMMAND tst_rayedragghost)" in tests
