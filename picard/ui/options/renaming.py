# -*- coding: utf-8 -*-
#
# Picard, the next-generation MusicBrainz tagger
#
# Copyright (C) 2006-2008, 2011 Lukáš Lalinský
# Copyright (C) 2008-2009 Nikolai Prokoschenko
# Copyright (C) 2009-2010, 2014-2015, 2018-2021 Philipp Wolfer
# Copyright (C) 2011-2013 Michael Wiencek
# Copyright (C) 2011-2013 Wieland Hoffmann
# Copyright (C) 2013 Calvin Walton
# Copyright (C) 2013 Ionuț Ciocîrlan
# Copyright (C) 2013-2014 Sophist-UK
# Copyright (C) 2013-2015, 2018-2021 Laurent Monin
# Copyright (C) 2015 Alex Berman
# Copyright (C) 2015 Ohm Patel
# Copyright (C) 2016 Suhas
# Copyright (C) 2016-2017 Sambhav Kothari
# Copyright (C) 2021 Bob Swift
# Copyright (C) 2021 Gabriel Ferreira
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.


from functools import partial
import os.path

from PyQt5 import QtWidgets
from PyQt5.QtCore import QStandardPaths
from PyQt5.QtGui import QPalette

from picard.config import (
    BoolOption,
    ListOption,
    TextOption,
    get_config,
)
from picard.const import DEFAULT_FILE_NAMING_FORMAT
from picard.const.sys import IS_WIN
from picard.script import ScriptParser

from picard.ui.options import (
    OptionsCheckError,
    OptionsPage,
    register_options_page,
)
from picard.ui.options.scripting import (
    ScriptCheckError,
    ScriptingDocumentationDialog,
)
from picard.ui.scripteditor import (
    ScriptEditorDialog,
    ScriptEditorExamples,
)
from picard.ui.ui_options_renaming import Ui_RenamingOptionsPage
from picard.ui.util import enabledSlot


_default_music_dir = QStandardPaths.writableLocation(QStandardPaths.MusicLocation)


class RenamingOptionsPage(OptionsPage):

    NAME = "filerenaming"
    TITLE = N_("File Naming")
    PARENT = None
    SORT_ORDER = 40
    ACTIVE = True
    HELP_URL = '/config/options_filerenaming.html'

    options = [
        BoolOption("setting", "windows_compatibility", True),
        BoolOption("setting", "ascii_filenames", False),
        BoolOption("setting", "rename_files", False),
        TextOption(
            "setting",
            "file_naming_format",
            DEFAULT_FILE_NAMING_FORMAT,
        ),
        BoolOption("setting", "move_files", False),
        TextOption("setting", "move_files_to", _default_music_dir),
        BoolOption("setting", "move_additional_files", False),
        TextOption("setting", "move_additional_files_pattern", "*.jpg *.png"),
        BoolOption("setting", "delete_empty_dirs", True),
        ListOption(
            "setting",
            "file_naming_scripts",
            [],
        ),
        TextOption(
            "setting",
            "selected_file_naming_script_id",
            "",
        ),
    ]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.script_text = ""
        self.ui = Ui_RenamingOptionsPage()
        self.ui.setupUi(self)

        self.ui.ascii_filenames.clicked.connect(self.update_examples_from_local)
        self.ui.windows_compatibility.clicked.connect(self.update_examples_from_local)
        self.ui.rename_files.clicked.connect(self.update_examples_from_local)
        self.ui.move_files.clicked.connect(self.update_examples_from_local)
        self.ui.move_files_to.editingFinished.connect(self.update_examples_from_local)

        self.ui.move_files.toggled.connect(
            partial(
                enabledSlot,
                self.toggle_file_moving
            )
        )
        self.ui.rename_files.toggled.connect(
            partial(
                enabledSlot,
                self.toggle_file_renaming
            )
        )
        self.ui.open_script_editor.clicked.connect(self.show_script_editing_page)
        self.ui.move_files_to_browse.clicked.connect(self.move_files_to_browse)

        self.ui.naming_script_selector.currentIndexChanged.connect(self.update_selector_in_editor)

        self.ui.example_filename_after.itemSelectionChanged.connect(self.match_before_to_after)
        self.ui.example_filename_before.itemSelectionChanged.connect(self.match_after_to_before)

        script_edit = self.ui.move_additional_files_pattern
        self.script_palette_normal = script_edit.palette()
        self.script_palette_readonly = QPalette(self.script_palette_normal)
        disabled_color = self.script_palette_normal.color(QPalette.Inactive, QPalette.Window)
        self.script_palette_readonly.setColor(QPalette.Disabled, QPalette.Base, disabled_color)

        self.ui.example_filename_sample_files_button.clicked.connect(self.update_example_files)

        self.examples = ScriptEditorExamples(tagger=self.tagger)

        self.ui.example_selection_note.setText(_(self.examples.notes_text) % self.examples.max_samples)
        self.ui.example_filename_sample_files_button.setToolTip(_(self.examples.tooltip_text) % self.examples.max_samples)

        self.script_editor_page = ScriptEditorDialog(parent=self, examples=self.examples)
        self.script_editor_page.signal_save.connect(self.save_from_editor)
        self.script_editor_page.signal_update.connect(self.update_from_editor)
        self.script_editor_page.signal_selection_changed.connect(self.update_selector_from_editor)

        self.update_selector_from_editor()

        # Sync example lists vertical scrolling and selection colors
        self.script_editor_page.synchronize_vertical_scrollbars((self.ui.example_filename_before, self.ui.example_filename_after))

        self.current_row = -1

    def update_selector_from_editor(self):
        """Update the script selector combo box from the script editor page.
        """
        self.ui.naming_script_selector.blockSignals(True)
        self.ui.naming_script_selector.clear()
        for i in range(self.script_editor_page.ui.preset_naming_scripts.count()):
            title = self.script_editor_page.ui.preset_naming_scripts.itemText(i)
            script = self.script_editor_page.ui.preset_naming_scripts.itemData(i)
            self.ui.naming_script_selector.addItem(title, script)
        self.ui.naming_script_selector.setCurrentIndex(self.script_editor_page.ui.preset_naming_scripts.currentIndex())
        self.ui.naming_script_selector.blockSignals(False)

    def update_selector_in_editor(self):
        """Update the selection in the script editor page to match local selection.
        """
        self.script_editor_page.ui.preset_naming_scripts.setCurrentIndex(self.ui.naming_script_selector.currentIndex())

    def match_after_to_before(self):
        """Sets the selected item in the 'after' list to the corresponding item in the 'before' list.
        """
        self.script_editor_page.synchronize_selected_example_lines(self.current_row, self.ui.example_filename_before, self.ui.example_filename_after)

    def match_before_to_after(self):
        """Sets the selected item in the 'before' list to the corresponding item in the 'after' list.
        """
        self.script_editor_page.synchronize_selected_example_lines(self.current_row, self.ui.example_filename_after, self.ui.example_filename_before)

    def show_script_editing_page(self):
        self.script_editor_page.show()
        self.script_editor_page.raise_()
        self.script_editor_page.activateWindow()
        self.update_examples_from_local()

    def show_scripting_documentation(self):
        ScriptingDocumentationDialog.show_instance(parent=self)

    def toggle_file_moving(self, state):
        self.toggle_file_naming_format()
        self.ui.delete_empty_dirs.setEnabled(state)
        self.ui.move_files_to.setEnabled(state)
        self.ui.move_files_to_browse.setEnabled(state)
        self.ui.move_additional_files.setEnabled(state)
        self.ui.move_additional_files_pattern.setEnabled(state)

    def toggle_file_renaming(self, state):
        self.toggle_file_naming_format()

    def toggle_file_naming_format(self):
        active = self.ui.move_files.isChecked() or self.ui.rename_files.isChecked()
        self.ui.open_script_editor.setEnabled(active)
        self.ui.ascii_filenames.setEnabled(active)
        if not IS_WIN:
            self.ui.windows_compatibility.setEnabled(active)

    def save_from_editor(self):
        self.script_text = self.script_editor_page.get_script()

    def update_from_editor(self):
        self.display_examples()

    def check_formats(self):
        self.test()
        self.update_examples_from_local()

    def update_example_files(self):
        self.examples.update_sample_example_files()
        self.script_editor_page.display_examples()

    def update_examples_from_local(self):
        override = {
            'ascii_filenames': self.ui.ascii_filenames.isChecked(),
            'move_files': self.ui.move_files.isChecked(),
            'move_files_to': os.path.normpath(self.ui.move_files_to.text()),
            'rename_files': self.ui.rename_files.isChecked(),
            'windows_compatibility': self.ui.windows_compatibility.isChecked(),
        }
        self.examples.update_examples(override=override)
        self.script_editor_page.display_examples()

    def display_examples(self):
        self.current_row = -1
        examples = self.examples.get_examples()
        self.script_editor_page.update_example_listboxes(self.ui.example_filename_before, self.ui.example_filename_after, examples)

    def load(self):
        config = get_config()
        if IS_WIN:
            self.ui.windows_compatibility.setChecked(True)
            self.ui.windows_compatibility.setEnabled(False)
        else:
            self.ui.windows_compatibility.setChecked(config.setting["windows_compatibility"])
        self.ui.rename_files.setChecked(config.setting["rename_files"])
        self.ui.move_files.setChecked(config.setting["move_files"])
        self.ui.ascii_filenames.setChecked(config.setting["ascii_filenames"])
        self.script_text = config.setting["file_naming_format"]
        self.ui.move_files_to.setText(config.setting["move_files_to"])
        self.ui.move_files_to.setCursorPosition(0)
        self.ui.move_additional_files.setChecked(config.setting["move_additional_files"])
        self.ui.move_additional_files_pattern.setText(config.setting["move_additional_files_pattern"])
        self.ui.delete_empty_dirs.setChecked(config.setting["delete_empty_dirs"])
        self.script_editor_page.load()
        self.update_examples_from_local()

    def check(self):
        self.check_format()
        if self.ui.move_files.isChecked() and not self.ui.move_files_to.text().strip():
            raise OptionsCheckError(_("Error"), _("The location to move files to must not be empty."))

    def check_format(self):
        parser = ScriptParser()
        try:
            parser.eval(self.script_text)
        except Exception as e:
            raise ScriptCheckError("", str(e))
        if self.ui.rename_files.isChecked():
            if not self.script_text.strip():
                raise ScriptCheckError("", _("The file naming format must not be empty."))

    def save(self):
        config = get_config()
        config.setting["windows_compatibility"] = self.ui.windows_compatibility.isChecked()
        config.setting["ascii_filenames"] = self.ui.ascii_filenames.isChecked()
        config.setting["rename_files"] = self.ui.rename_files.isChecked()
        config.setting["file_naming_format"] = self.script_text.strip()
        self.tagger.window.enable_renaming_action.setChecked(config.setting["rename_files"])
        config.setting["move_files"] = self.ui.move_files.isChecked()
        config.setting["move_files_to"] = os.path.normpath(self.ui.move_files_to.text())
        config.setting["move_additional_files"] = self.ui.move_additional_files.isChecked()
        config.setting["move_additional_files_pattern"] = self.ui.move_additional_files_pattern.text()
        config.setting["delete_empty_dirs"] = self.ui.delete_empty_dirs.isChecked()
        config.setting["file_naming_scripts"] = self.script_editor_page.naming_scripts
        config.setting["selected_file_naming_script_id"] = self.script_editor_page.selected_script_id
        self.tagger.window.enable_moving_action.setChecked(config.setting["move_files"])

    def display_error(self, error):
        # Ignore scripting errors, those are handled inline
        if not isinstance(error, ScriptCheckError):
            super().display_error(error)

    def move_files_to_browse(self):
        path = QtWidgets.QFileDialog.getExistingDirectory(self, "", self.ui.move_files_to.text())
        if path:
            path = os.path.normpath(path)
            self.ui.move_files_to.setText(path)

    def test(self):
        self.ui.renaming_error.setStyleSheet("")
        self.ui.renaming_error.setText("")
        try:
            self.check_format()
        except ScriptCheckError as e:
            self.ui.renaming_error.setStyleSheet(self.STYLESHEET_ERROR)
            self.ui.renaming_error.setText(e.info)
            return


register_options_page(RenamingOptionsPage)
