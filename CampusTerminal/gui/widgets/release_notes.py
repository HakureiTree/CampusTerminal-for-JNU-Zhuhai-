# SPDX-License-Identifier: GPL-3.0-or-later
"""Read-only Markdown release notes and their layout measurements."""
from math import ceil
import re

from PyQt5.QtCore import QSize
from PyQt5.QtGui import (
    QAbstractTextDocumentLayout, QColor, QFont, QPainter, QPalette,
    QTextCharFormat, QTextCursor, QTextDocument, QTextOption)
from PyQt5.QtWidgets import QSizePolicy, QWidget


_HEADING = re.compile(r"^(#{1,6})[ \t]*(\S.*?)\s*$")


def _markdown(notes):
    lines = notes.replace("\r\n", "\n").replace("\r", "\n").strip().splitlines()
    for index, line in enumerate(lines):
        if line.strip() in ("更新", "修复"):
            lines[index] = "## " + line.strip()
        else:
            heading = _HEADING.match(line)
            if heading:
                lines[index] = heading[1] + " " + heading[2]
    if lines and not _HEADING.match(lines[0]):
        # The release extractor supplies the body of the first 更新 section.
        lines[:0] = ["## 更新", ""]
    return "\n".join(lines)


class ReleaseNotes(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.document = QTextDocument(self)
        self.document.setDocumentMargin(0)
        option = self.document.defaultTextOption()
        option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.document.setDefaultTextOption(option)
        self._notes = ""
        self._heading_font = QFont(self.font())
        policy = QSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)

    def set_notes(self, notes):
        self._notes = _markdown(notes)
        self._render()

    def set_presentation(self, body_font, heading_font):
        if self.font() != body_font or self._heading_font != heading_font:
            self.setFont(body_font)
            self._heading_font = QFont(heading_font)
            self._render()

    def text(self):
        return self.document.toPlainText()

    def _render(self):
        self.document.setDefaultFont(self.font())
        self.document.setIndentWidth(max(12, self.fontMetrics().height()))
        self.document.setMarkdown(
            self._notes, QTextDocument.MarkdownFeatures(
                QTextDocument.MarkdownDialectGitHub | QTextDocument.MarkdownNoHTML))
        block = self.document.begin()
        while block.isValid():
            cursor = QTextCursor(block)
            fmt = block.blockFormat()
            level = fmt.headingLevel()
            fmt.setTopMargin(self.fontMetrics().height() if level and block.position() else 0)
            fmt.setBottomMargin(max(3, self.fontMetrics().height() // 3))
            cursor.setBlockFormat(fmt)
            if level:
                heading = QFont(self._heading_font)
                if level > 2:
                    heading.setPixelSize(max(self.font().pixelSize(), heading.pixelSize() - 1))
                char_format = QTextCharFormat()
                char_format.setFont(heading)
                char_format.setForeground(QColor("#c7c7c7"))
                cursor.select(QTextCursor.BlockUnderCursor)
                cursor.setCharFormat(char_format)
            block = block.next()
        self.updateGeometry()
        self.update()

    def natural_width(self):
        self.document.setTextWidth(-1)
        return ceil(self.document.idealWidth())

    def heightForWidth(self, width):
        self.document.setTextWidth(max(1, width))
        return ceil(self.document.size().height())

    def sizeHint(self):
        width = self.natural_width()
        return QSize(width, self.heightForWidth(width))

    def paintEvent(self, _event):
        self.document.setTextWidth(max(1, self.width()))
        context = QAbstractTextDocumentLayout.PaintContext()
        context.palette.setColor(QPalette.Text, QColor("#c6c6c6"))
        painter = QPainter(self)
        self.document.documentLayout().draw(painter, context)
