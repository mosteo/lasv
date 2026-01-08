#!/usr/bin/env python3
"""
GUI viewer for LASV (LLM-Assisted Semantic Versioning) analysis results.

This module provides a PyQt6-based tree view to browse crates, releases,
and their analysis results stored in lasv.yaml.
"""

import sys
import yaml
import difflib
from pathlib import Path
from typing import Any, Optional

try:
    from PyQt6.QtWidgets import (
        QApplication, QMainWindow, QTreeView, QTextEdit, QSplitter,
        QVBoxLayout, QHBoxLayout, QWidget, QPushButton, QLineEdit,
        QLabel, QMessageBox, QToolBar, QMenu, QCheckBox
    )
    from PyQt6.QtCore import (
        Qt, QAbstractItemModel, QModelIndex, pyqtSignal
    )
    from PyQt6.QtGui import QAction, QIcon, QFont, QColor
except ImportError:
    print("Error: PyQt6 is not installed.")
    print("Please install it with: pip install PyQt6")
    sys.exit(1)


class LasvTreeItem:
    """Represents a node in the tree structure."""

    def __init__(self, data: Any, parent: Optional['LasvTreeItem'] = None):
        self.data = data
        self.parent = parent
        self.children: list['LasvTreeItem'] = []
        self.item_type = ""  # 'crate', 'release', 'pair', 'analysis'
        self.display_name = ""

    def add_child(self, child: 'LasvTreeItem'):
        """Add a child item."""
        self.children.append(child)

    def child(self, row: int) -> Optional['LasvTreeItem']:
        """Get child at specified row."""
        if 0 <= row < len(self.children):
            return self.children[row]
        return None

    def child_count(self) -> int:
        """Return number of children."""
        return len(self.children)

    def row(self) -> int:
        """Return row number in parent."""
        if self.parent:
            return self.parent.children.index(self)
        return 0


class LasvTreeModel(QAbstractItemModel):
    """Tree model for LASV data."""

    def __init__(self, yaml_path: str = "lasv.yaml"):
        super().__init__()
        self.yaml_path = yaml_path
        self.root_item = LasvTreeItem({"name": "Root"})
        self.filter_empty_crates = True  # Filter enabled by default
        self.filter_no_changes = True  # Filter enabled by default
        self.load_data()

    def load_data(self):
        """Load data from lasv.yaml and build tree structure."""
        self.beginResetModel()
        self.root_item = LasvTreeItem({"name": "Root"})

        try:
            with open(self.yaml_path, 'r') as f:
                data = yaml.safe_load(f)

            if not data or 'crates' not in data:
                self.endResetModel()
                return

            crates = data['crates']

            # Build tree structure
            for crate_name, crate_data in sorted(crates.items()):
                crate_item = LasvTreeItem(crate_data, self.root_item)
                crate_item.item_type = "crate"
                crate_item.display_name = crate_name

                # Add crate metadata as info
                info_parts = []
                if crate_data.get('binary'):
                    info_parts.append("binary")
                if crate_data.get('external'):
                    info_parts.append("external")
                if crate_data.get('last_version'):
                    info_parts.append(f"v{crate_data['last_version']}")

                if info_parts:
                    crate_item.display_name += f" ({', '.join(info_parts)})"

                # Track if crate has any releases/pairs
                has_content = False

                # Add releases
                releases = crate_data.get('releases', {})
                for release_version, release_data in sorted(releases.items()):
                    release_item = LasvTreeItem(release_data, crate_item)
                    release_item.item_type = "release"
                    release_item.display_name = f"Release {release_version}"

                    # Track if this release has any diagnosis with changes
                    release_has_changes = False

                    # Add release-level diagnosis/summary/changes as children
                    if release_data.get('diagnosis'):
                        diag_item = LasvTreeItem(release_data['diagnosis'], release_item)
                        diag_item.item_type = "diagnosis"
                        diag_item.display_name = "Diagnosis"

                        # Track if diagnosis has any analyzers with changes
                        diag_has_analyzers = False

                        # Add each analyzer (files, model names) under diagnosis
                        diagnosis_data = release_data['diagnosis']
                        if isinstance(diagnosis_data, dict):
                            for analyzer_name, analyzer_data in sorted(diagnosis_data.items()):
                                if isinstance(analyzer_data, dict):
                                    # Check if filter is enabled and analyzer has no changes
                                    changes = analyzer_data.get('changes', [])
                                    has_changes = isinstance(changes, list) and len(changes) > 0

                                    if self.filter_no_changes and not has_changes:
                                        continue  # Skip this analyzer

                                    analyzer_item = LasvTreeItem(analyzer_data, diag_item)
                                    analyzer_item.item_type = "analyzer"
                                    analyzer_item.display_name = analyzer_name
                                    diag_item.add_child(analyzer_item)
                                    diag_has_analyzers = True
                                    release_has_changes = True

                                    # Add compliance info
                                    if 'compliant' in analyzer_data:
                                        comp_item = LasvTreeItem({'text': analyzer_data['compliant']}, analyzer_item)
                                        comp_item.item_type = "compliance"
                                        comp_item.display_name = f"Compliance: {analyzer_data['compliant']}"
                                        analyzer_item.add_child(comp_item)

                                    # Add noncompliance reason if present
                                    if 'noncompliance' in analyzer_data:
                                        noncomp_item = LasvTreeItem({'text': analyzer_data['noncompliance']}, analyzer_item)
                                        noncomp_item.item_type = "noncompliance"
                                        noncomp_item.display_name = "Noncompliance Reason"
                                        analyzer_item.add_child(noncomp_item)

                                    # Add changes
                                    if 'changes' in analyzer_data:
                                        changes_item = LasvTreeItem({'text': analyzer_data['changes']}, analyzer_item)
                                        changes_item.item_type = "changes"
                                        changes_count = len(analyzer_data['changes']) if isinstance(analyzer_data['changes'], list) else 0
                                        changes_item.display_name = f"Changes ({changes_count})"
                                        analyzer_item.add_child(changes_item)

                                        # Add individual changes as children
                                        if isinstance(analyzer_data['changes'], list):
                                            for change in analyzer_data['changes']:
                                                if isinstance(change, dict):
                                                    severity = change.get('severity', 'UNKNOWN')
                                                    description = change.get('description', 'No description')
                                                    line = change.get('line', 0)
                                                    col = change.get('col', 0)

                                                    change_child_item = LasvTreeItem(change, changes_item)
                                                    change_child_item.item_type = "change_item"
                                                    change_child_item.display_name = f"{severity} ({line}, {col}): {description}"
                                                    changes_item.add_child(change_child_item)

                        # Only add diagnosis if it has analyzers (when filter is enabled)
                        if diag_has_analyzers or not self.filter_no_changes:
                            release_item.add_child(diag_item)
                    if release_data.get('summary'):
                        summary_item = LasvTreeItem({'text': release_data['summary']}, release_item)
                        summary_item.item_type = "summary"
                        summary_item.display_name = "Summary"
                        release_item.add_child(summary_item)
                    if release_data.get('changes'):
                        changes_item = LasvTreeItem({'text': release_data['changes']}, release_item)
                        changes_item.item_type = "changes"
                        changes_item.display_name = "Changes"
                        release_item.add_child(changes_item)

                    # Add pairs
                    pairs = release_data.get('pairs', {})
                    for pair_key, pair_data in sorted(pairs.items()):
                        pair_item = LasvTreeItem(pair_data, release_item)
                        pair_item.item_type = "pair"

                        # Format pair display name
                        from_ver = pair_key
                        to_ver = release_version
                        pair_item.display_name = f"{from_ver} → {to_ver}"

                        # Add analysis status indicator
                        if pair_data.get('diagnosis'):
                            pair_item.display_name += " ✓"
                        else:
                            pair_item.display_name += " ⧗"

                        release_item.add_child(pair_item)
                        release_has_changes = True  # Pairs count as content

                        # Add analysis details as children
                        if pair_data.get('diagnosis'):
                            diag_item = LasvTreeItem(
                                {'text': pair_data['diagnosis']},
                                pair_item
                            )
                            diag_item.item_type = "diagnosis"
                            diag_item.display_name = "Diagnosis"
                            pair_item.add_child(diag_item)

                        if pair_data.get('summary'):
                            summary_item = LasvTreeItem(
                                {'text': pair_data['summary']},
                                pair_item
                            )
                            summary_item.item_type = "summary"
                            summary_item.display_name = "Summary"
                            pair_item.add_child(summary_item)

                        if pair_data.get('changes'):
                            changes_item = LasvTreeItem(
                                {'text': pair_data['changes']},
                                pair_item
                            )
                            changes_item.item_type = "changes"
                            changes_item.display_name = "Changes"
                            pair_item.add_child(changes_item)

                    # Only add release if it has content or filter is disabled
                    if release_has_changes or release_item.child_count() > 0 or not self.filter_no_changes:
                        crate_item.add_child(release_item)
                        has_content = True  # Crate has at least one release with content

                # Only add crate if it has content or filter is disabled
                if has_content or not self.filter_empty_crates:
                    self.root_item.add_child(crate_item)

        except FileNotFoundError:
            print(f"Warning: {self.yaml_path} not found")
        except Exception as e:
            print(f"Error loading data: {e}")

        self.endResetModel()

    def set_filter_empty_crates(self, enabled: bool):
        """Enable or disable filtering of empty crates."""
        self.filter_empty_crates = enabled
        self.load_data()  # Reload data with new filter setting

    def set_filter_no_changes(self, enabled: bool):
        """Enable or disable filtering of diagnosis with no changes."""
        self.filter_no_changes = enabled
        self.load_data()  # Reload data with new filter setting

    def index(self, row: int, column: int, parent: QModelIndex = QModelIndex()) -> QModelIndex:
        """Create index for item at row, column under parent."""
        if not self.hasIndex(row, column, parent):
            return QModelIndex()

        if not parent.isValid():
            parent_item = self.root_item
        else:
            parent_item = parent.internalPointer()

        child_item = parent_item.child(row)
        if child_item:
            return self.createIndex(row, column, child_item)
        return QModelIndex()

    def parent(self, index: QModelIndex) -> QModelIndex:
        """Return parent index of given index."""
        if not index.isValid():
            return QModelIndex()

        child_item = index.internalPointer()
        parent_item = child_item.parent

        if parent_item == self.root_item or parent_item is None:
            return QModelIndex()

        return self.createIndex(parent_item.row(), 0, parent_item)

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """Return number of rows under parent."""
        if parent.column() > 0:
            return 0

        if not parent.isValid():
            parent_item = self.root_item
        else:
            parent_item = parent.internalPointer()

        return parent_item.child_count()

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:
        """Return number of columns."""
        return 1

    def data(self, index: QModelIndex, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """Return data for given index and role."""
        if not index.isValid():
            return None

        item = index.internalPointer()

        if role == Qt.ItemDataRole.DisplayRole:
            return item.display_name
        elif role == Qt.ItemDataRole.ForegroundRole:
            # Color coding based on item type
            if item.item_type == "crate":
                if item.data.get('binary') or item.data.get('external'):
                    return QColor(150, 150, 150)  # Gray for binary/external
            elif item.item_type == "pair":
                if item.data.get('diagnosis'):
                    return QColor(0, 150, 0)  # Green for analyzed
                else:
                    return QColor(200, 100, 0)  # Orange for pending
            elif item.item_type in ["diagnosis", "summary", "changes"]:
                return QColor(0, 120, 200)  # Blue-ish for analysis nodes
            elif item.item_type == "analyzer":
                return QColor(100, 100, 200)  # Purple-ish for analyzers
            elif item.item_type == "compliance":
                # Color based on compliance value
                compliant = item.data.get('text', '')
                if compliant == "strict":
                    return QColor(0, 180, 0)  # Green for strict compliance
                elif compliant == "lax":
                    return QColor(200, 150, 0)  # Yellow-ish for lax
                else:  # "no"
                    return QColor(200, 0, 0)  # Red for non-compliant
            elif item.item_type == "noncompliance":
                return QColor(200, 0, 0)  # Red for noncompliance reason
            elif item.item_type == "change_item":
                # Color based on severity
                severity = item.data.get('severity', '')
                if severity == "MAJOR":
                    return QColor(200, 0, 0)  # Red for MAJOR changes
                elif severity == "minor":
                    return QColor(0, 150, 0)  # Green for minor changes

        return None

    def headerData(self, section: int, orientation: Qt.Orientation, role: int = Qt.ItemDataRole.DisplayRole) -> Any:
        """Return header data."""
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return "LASV Analysis Tree"
        return None


class DetailPanel(QTextEdit):
    """Panel to display detailed information about selected item."""

    def __init__(self):
        super().__init__()
        self.setReadOnly(True)
        self.setFont(QFont("Monospace", 10))

    def display_item(self, item: LasvTreeItem):
        """Display details of the selected item."""
        if not item:
            self.clear()
            return

        # Helper to stringify nested structures safely
        def _str(val) -> str:
            if isinstance(val, (dict, list)):
                return yaml.safe_dump(val, sort_keys=False)
            if val is None:
                return ""
            return str(val)

        content = []
        content.append(f"Type: {item.item_type.upper()}")
        content.append(f"Name: {item.display_name}")
        content.append("-" * 60)

        if item.item_type == "change_item":
            # Display the file with line numbers for individual changes
            filename = item.data.get('filename', '')
            line = item.data.get('line', 0)
            col = item.data.get('col', 0)
            severity = item.data.get('severity', 'UNKNOWN')
            description = item.data.get('description', 'No description')

            content.append(f"Severity: {severity}")
            content.append(f"Description: {description}")
            if filename:
                content.append(f"File: {filename}")
            if line > 0 or col > 0:
                content.append(f"Location: line {line}, col {col}")
            content.append("-" * 60)

            # Try to read and display the file with line numbers
            if filename and Path(filename).exists():
                try:
                    with open(filename, 'r', encoding='utf-8') as f:
                        file_lines = f.readlines()

                    content.append(f"\nFile content ({len(file_lines)} lines):\n")
                    for i, file_line in enumerate(file_lines, 1):
                        # Highlight the line where the change is
                        if i == line:
                            content.append(f">>> {i:4d}: {file_line.rstrip()}")
                        else:
                            content.append(f"    {i:4d}: {file_line.rstrip()}")
                except Exception as e:
                    content.append(f"\nError reading file: {e}")
            elif filename:
                content.append(f"\nFile not found: {filename}")
        elif item.item_type == "changes":
            # Display changes in a formatted way
            changes = item.data.get('text', [])
            if isinstance(changes, list):
                content.append(f"Total changes: {len(changes)}\n")
                for i, change in enumerate(changes, 1):
                    if isinstance(change, dict):
                        severity = change.get('severity', 'UNKNOWN')
                        description = change.get('description', 'No description')
                        line = change.get('line', 0)
                        col = change.get('col', 0)
                        filename = change.get('filename', '')

                        content.append(f"[{i}] {severity}")
                        if filename:
                            content.append(f"    File: {filename}")
                        if line > 0 or col > 0:
                            content.append(f"    Location: line {line}, col {col}")
                        content.append(f"    {description}")
                        content.append("")  # Empty line for spacing
            else:
                content.append(_str(changes))
        elif item.item_type in ["diagnosis", "summary", "compliance", "noncompliance"]:
            # Display the text content (stringify nested structures)
            text = item.data.get('text', '')
            content.append(_str(text))
        elif item.item_type == "analyzer":
            # Display analyzer (model) information
            content.append(f"Analyzer: {item.display_name}")
            content.append(f"\nAnalyzer Data:")
            for key, value in item.data.items():
                if key not in ['changes']:
                    content.append(f"{key}: {_str(value)}")
            if 'changes' in item.data:
                content.append(f"\nNumber of changes: {len(item.data.get('changes', []))}")
        elif item.item_type == "pair":
            # Display pair information
            content.append(f"Pair Data:")
            for key, value in item.data.items():
                if key in ['diagnosis', 'summary', 'changes']:
                    content.append(f"\n{key.upper()}:")
                    content.append(_str(value))
                else:
                    content.append(f"{key}: {_str(value)}")
        elif item.item_type == "release":
            content.append(f"Release Data:")
            for key, value in item.data.items():
                if key != 'pairs':
                    content.append(f"{key}: {_str(value)}")
            content.append(f"\nNumber of pairs: {len(item.data.get('pairs', {}))}")
        elif item.item_type == "crate":
            content.append(f"Crate Information:")
            for key, value in item.data.items():
                if key != 'releases':
                    content.append(f"{key}: {_str(value)}")
            content.append(f"\nNumber of releases: {len(item.data.get('releases', {}))}")

        self.setPlainText("\n".join(content))

    def display_diff(self, item: LasvTreeItem):
        """Display unified diff for a change item."""
        if not item:
            self.clear()
            return

        filename = item.data.get('filename', '')
        old_filename = item.data.get('old_filename', '')
        severity = item.data.get('severity', 'UNKNOWN')
        description = item.data.get('description', 'No description')
        line = item.data.get('line', 0)
        col = item.data.get('col', 0)

        content = []
        content.append(f"Type: DIFF")
        content.append(f"Severity: {severity}")
        content.append(f"Description: {description}")
        if line > 0 or col > 0:
            content.append(f"Location: line {line}, col {col}")
        content.append("=" * 60)

        # Handle edge cases
        if not old_filename and not filename:
            content.append("\nNo files to compare.")
            self.setPlainText("\n".join(content))
            return

        if not old_filename:
            # File was added
            content.append(f"\nFile added: {filename}")
            content.append("\n[New file content:]")
            if Path(filename).exists():
                try:
                    with open(filename, 'r', encoding='utf-8') as f:
                        file_lines = f.readlines()
                    for i, file_line in enumerate(file_lines, 1):
                        content.append(f"+ {i:4d}: {file_line.rstrip()}")
                except Exception as e:
                    content.append(f"\nError reading new file: {e}")
            else:
                content.append(f"\nFile not found: {filename}")
            self.setPlainText("\n".join(content))
            return

        if not filename:
            # File was removed
            content.append(f"\nFile removed: {old_filename}")
            content.append("\n[Old file content:]")
            if Path(old_filename).exists():
                try:
                    with open(old_filename, 'r', encoding='utf-8') as f:
                        file_lines = f.readlines()
                    for i, file_line in enumerate(file_lines, 1):
                        content.append(f"- {i:4d}: {file_line.rstrip()}")
                except Exception as e:
                    content.append(f"\nError reading old file: {e}")
            else:
                content.append(f"\nFile not found: {old_filename}")
            self.setPlainText("\n".join(content))
            return

        # Both files exist - generate diff
        content.append(f"\n--- {old_filename}")
        content.append(f"+++ {filename}")
        content.append("")

        if not Path(old_filename).exists():
            content.append(f"\nOld file not found: {old_filename}")
            self.setPlainText("\n".join(content))
            return

        if not Path(filename).exists():
            content.append(f"\nNew file not found: {filename}")
            self.setPlainText("\n".join(content))
            return

        try:
            with open(old_filename, 'r', encoding='utf-8') as f:
                old_lines = f.readlines()
            with open(filename, 'r', encoding='utf-8') as f:
                new_lines = f.readlines()

            # Generate unified diff
            diff = difflib.unified_diff(
                old_lines,
                new_lines,
                fromfile=old_filename,
                tofile=filename,
                lineterm='',
                n=3  # 3 context lines
            )

            # Skip the first two lines (file headers) as we already added them
            diff_lines = list(diff)
            for diff_line in diff_lines[2:]:  # Skip --- and +++ lines
                content.append(diff_line.rstrip())

        except Exception as e:
            content.append(f"\nError generating diff: {e}")

        self.setPlainText("\n".join(content))


class MainWindow(QMainWindow):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("LASV Viewer - LLM-Assisted Semantic Versioning")
        self.setGeometry(100, 100, 1200, 800)

        # Create model
        self.model = LasvTreeModel()

        # Create UI
        self.setup_ui()

    def setup_ui(self):
        """Set up the user interface."""
        # Create central widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        # Create main layout
        main_layout = QVBoxLayout(central_widget)

        # Create button bar at the top
        button_bar = QWidget()
        button_bar.setMaximumHeight(35)  # Limit height to single line
        button_layout = QHBoxLayout(button_bar)
        button_layout.setContentsMargins(5, 2, 5, 2)
        button_layout.setSpacing(5)

        # Add filter checkbox
        self.filter_checkbox = QCheckBox("Hide empty crates")
        self.filter_checkbox.setChecked(True)  # Enabled by default
        self.filter_checkbox.setToolTip("Hide crates that have no releases or pairs")
        self.filter_checkbox.stateChanged.connect(self.toggle_filter)
        button_layout.addWidget(self.filter_checkbox)

        # Add filter for no changes checkbox
        self.filter_no_changes_checkbox = QCheckBox("Hide empty diagnosis")
        self.filter_no_changes_checkbox.setChecked(True)  # Enabled by default
        self.filter_no_changes_checkbox.setToolTip("Hide diagnosis/analyzers that have no changes")
        self.filter_no_changes_checkbox.stateChanged.connect(self.toggle_no_changes_filter)
        button_layout.addWidget(self.filter_no_changes_checkbox)

        # Add separator
        button_layout.addSpacing(10)

        # Add refresh button
        refresh_btn = QPushButton("Refresh")
        refresh_btn.setMaximumWidth(80)
        refresh_btn.clicked.connect(self.refresh_data)
        button_layout.addWidget(refresh_btn)

        # Add expand/collapse buttons
        expand_btn = QPushButton("Expand All")
        expand_btn.setMaximumWidth(90)
        expand_btn.clicked.connect(self.expand_all)
        button_layout.addWidget(expand_btn)

        collapse_btn = QPushButton("Collapse All")
        collapse_btn.setMaximumWidth(100)
        collapse_btn.clicked.connect(self.collapse_all)
        button_layout.addWidget(collapse_btn)

        # Add stretch to push buttons to the left
        button_layout.addStretch()

        # Add search box
        search_label = QLabel("Search:")
        button_layout.addWidget(search_label)
        self.search_box = QLineEdit()
        self.search_box.setPlaceholderText("Filter crates...")
        self.search_box.setMaximumWidth(200)
        self.search_box.textChanged.connect(self.filter_tree)
        button_layout.addWidget(self.search_box)

        main_layout.addWidget(button_bar)
        main_layout.setSpacing(0)

        # Create splitter for tree and detail panel
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # Create tree view
        self.tree_view = QTreeView()
        self.tree_view.setModel(self.model)
        self.tree_view.setHeaderHidden(False)
        self.tree_view.clicked.connect(self.on_item_clicked)
        self.tree_view.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree_view.customContextMenuRequested.connect(self.on_context_menu)
        splitter.addWidget(self.tree_view)

        # Create detail panel
        self.detail_panel = DetailPanel()
        splitter.addWidget(self.detail_panel)

        # Set splitter sizes (60% tree, 40% detail)
        splitter.setSizes([720, 480])

        main_layout.addWidget(splitter)

        # Status bar
        self.statusBar().showMessage("Ready")

    def on_item_clicked(self, index: QModelIndex):
        """Handle item click in tree view."""
        if index.isValid():
            item = index.internalPointer()
            self.detail_panel.display_item(item)
            self.statusBar().showMessage(f"Selected: {item.display_name}")

    def on_context_menu(self, position):
        """Handle context menu for tree view."""
        index = self.tree_view.indexAt(position)
        if not index.isValid():
            return

        item = index.internalPointer()

        # Only show context menu for change_item types
        if item.item_type == "change_item":
            menu = QMenu()
            show_diff_action = menu.addAction("Show Diff")
            action = menu.exec(self.tree_view.viewport().mapToGlobal(position))

            if action == show_diff_action:
                self.show_diff_for_item(item)

    def show_diff_for_item(self, item: LasvTreeItem):
        """Show diff for a change item."""
        filename = item.data.get('filename', '')
        old_filename = item.data.get('old_filename', '')

        # Use the DetailPanel's display_diff method
        self.detail_panel.display_diff(item)
        self.statusBar().showMessage(f"Showing diff for: {item.display_name}")

    def refresh_data(self):
        """Reload data from lasv.yaml."""
        self.model.load_data()
        self.statusBar().showMessage("Data refreshed")

    def expand_all(self):
        """Expand all tree items."""
        self.tree_view.expandAll()
        self.statusBar().showMessage("Expanded all items")

    def collapse_all(self):
        """Collapse all tree items."""
        self.tree_view.collapseAll()
        self.statusBar().showMessage("Collapsed all items")

    def toggle_filter(self, state: int):
        """Toggle the empty crates filter."""
        enabled = state == Qt.CheckState.Checked.value
        self.model.set_filter_empty_crates(enabled)
        if enabled:
            self.statusBar().showMessage("Hiding empty crates")
        else:
            self.statusBar().showMessage("Showing all crates")

    def toggle_no_changes_filter(self, state: int):
        """Toggle the filter for diagnosis with no changes."""
        enabled = state == Qt.CheckState.Checked.value
        self.model.set_filter_no_changes(enabled)
        if enabled:
            self.statusBar().showMessage("Hiding diagnosis with no changes")
        else:
            self.statusBar().showMessage("Showing all diagnosis")

    def filter_tree(self, text: str):
        """Filter tree based on search text."""
        # Simple implementation: just update status
        # A full implementation would require a proxy model
        if text:
            self.statusBar().showMessage(f"Filtering by: {text}")
        else:
            self.statusBar().showMessage("Ready")


def main():
    """Main entry point for the application."""
    app = QApplication(sys.argv)

    # Check if lasv.yaml exists
    if not Path("lasv.yaml").exists():
        msg = QMessageBox()
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setText("lasv.yaml not found in current directory")
        msg.setInformativeText("Please run this from the directory containing lasv.yaml")
        msg.setWindowTitle("File Not Found")
        msg.exec()
        return 1

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
