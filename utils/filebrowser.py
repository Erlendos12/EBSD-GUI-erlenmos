"""Utility for accessing a File Browser that is native to the OS"""
import os
import sys
from typing import Optional

from PySide6.QtCore import QDir
from PySide6.QtWidgets import QFileDialog, QWidget


class FileBrowser(QWidget):
    """Utility for accessing a File Browser that is native to the OS"""

    OpenFile = 0
    OpenFiles = 1
    OpenDirectory = 2
    SaveFile = 3

    def __init__(
        self,
        mode: Optional[int] = OpenFile,
        dirpath: Optional[str] = QDir.currentPath(),
        filter_name: Optional[str] = "All files (*.*)",
        caption: Optional[str] | None = None,
    ):
        """
        Utility for accessing a File Browser that is native to the OS

        Parameters
        ----------
        mode: int, optional
            The mode of the File Browser, which may be either OpenFile,
            OpenFiles, OpenDirectory, or SaveFile
        dirpath: str, optional
            The directory that is first shown in the File Browser
        filter_name: str, optional
            The filter that includes file extentions, which decides what
            files are shown, *or* allowed to be saved.
        caption: str, optional
            The title of the File Browser window
        """
        QWidget.__init__(self)
        self.browser_mode = mode
        if os.path.exists(dirpath):
            self.dirpath = dirpath
        else:
            self.dirpath = QDir.currentPath()
        self.filter_name = filter_name
        self.caption = caption

    def setMode(self, browser_mode: int):
        """
        Sets the mode, which may be either OpenFile, OpenFiles, 
        OpenDirectory, or SaveFile
        """
        self.browser_mode = browser_mode

    def setFileFilter(self, text: str):
        """Sets the filter of file extentions """
        self.filter_name = text

    def setDefaultDir(self, path: str):
        """Sets the default directory if the path exsits"""
        if os.path.exists(path):
            self.dirpath = path

    def setCaption(self, caption):
        """Sets the title of the File Browser window"""
        self.caption = caption

    def getFile(self) -> int:
        """
        Prompts the user with the File Browser window in the 
        currently set mode

        Returns
        -------
        int
            1 if one or more paths are set. Abort/ cancel returns 0
        """
        cap = self.caption
        self.filepaths: list[str] = []
        if self.browser_mode == FileBrowser.OpenFile:
            self.filepaths.append(
                QFileDialog.getOpenFileName(
                    self,
                    caption=cap if cap else "Choose File",
                    dir=self.dirpath,
                    filter=self.filter_name,
                )[0]
            )
        elif self.browser_mode == FileBrowser.OpenFiles:
            self.filepaths.extend(
                QFileDialog.getOpenFileNames(
                    self,
                    caption=cap if cap else "Choose Files",
                    dir=self.dirpath,
                    filter=self.filter_name,
                )[0]
            )
        elif self.browser_mode == FileBrowser.OpenDirectory:
            self.filepaths.append(
                QFileDialog.getExistingDirectory(
                    self, caption=cap if cap else "Choose Directory", dir=self.dirpath
                )
            )
        elif self.browser_mode == FileBrowser.SaveFile:
            options = QFileDialog.options(QFileDialog())
            if sys.platform == "darwin":
                options |= QFileDialog.DontUseNativeDialog
            self.filepaths.append(
                QFileDialog.getSaveFileName(
                    self,
                    caption=cap if cap else "Save/Save As",
                    dir=self.dirpath,
                    filter=self.filter_name,
                    options=options,
                )[0]
            )
        if not len(self.filepaths) or False in (len(path) for path in self.filepaths):
            return 0
        return 1

    def getPaths(self) -> list[str]:
        """
        Get the path which was last set by the 
        `utils.filebrowser.FileBrowser.getFile` method

        Returns
        -------
        List[str]
            A list which contains all the paths that were set
        """
        return self.filepaths
