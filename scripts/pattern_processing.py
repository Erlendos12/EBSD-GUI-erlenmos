"""
Script for a dialog window where users can specify parameters for 
Signal-to-Noise Improvements to be performed on a dataset"""
import gc
import os
from typing import Optional

import kikuchipy as kp
from kikuchipy.signals.ebsd import EBSD, LazyEBSD
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QMessageBox, QMainWindow

from ui.ui_pattern_processing import Ui_PatternProcessingDialog
from utils import FileBrowser, sendToJobManager


class PatternProcessingDialog(QDialog):
    """
    Dialog window where users can specify parameters for
    Signal-to-Noise Improvements to be performed on a dataset
    """

    def __init__(self, parent: QMainWindow, pattern_path: str):
        """
        Dialog window where users can specify parameters for
        Signal-to-Noise Improvements to be performed on a dataset

        Parameters
        ----------
        parent: QMainWindow
            The main application window
        pattern_path: str
            The path to the dataset that is to be indexed
        """
        super().__init__(parent)

        self.working_dir = os.path.dirname(pattern_path)
        self.pattern_name = os.path.basename(pattern_path)
        self.pattern_path = pattern_path
        self.filenamebase = os.path.basename(self.pattern_path).split(".")[0]

        # Standard filename of processed pattern
        self.save_path = os.path.join(self.working_dir, f"{self.filenamebase}.h5")

        # Overview of whether the file already is processed
        self.already_indexed = {"sb": False, "db": False, "anp": False}

        self.ui = Ui_PatternProcessingDialog()
        self.ui.setupUi(self)
        self.setWindowTitle(f"{self.windowTitle()} - {self.pattern_path}")
        self.setupConnections()

        try:
            self.s_preview: LazyEBSD = kp.load(self.pattern_path, lazy=True)
        except Exception as e:
            raise e

        self.showImage(self.s_preview.inav[1, 1])

        self.gaussian_window = kp.filters.Window("gaussian", std=1)

        self.fileBrowser = FileBrowser(
            mode=FileBrowser.SaveFile,
            dirpath=self.working_dir,
            filter_name="Hierarchical Data Format (*.h5);;NordifUF Pattern Files (*.dat)",
        )

        self.setupInitialSettings()

    def setupConnections(self):
        """Connects class methods to UI signals"""
        self.ui.browseButton.clicked.connect(lambda: self.setSavePath())
        self.ui.buttonBox.accepted.connect(lambda: self.run_processing())
        self.ui.buttonBox.rejected.connect(lambda: self.close_dialog())
        self.ui.folderEdit.setText(self.working_dir)
        self.ui.filenameEdit.setText(os.path.basename(self.save_path))

        # Whenever user checks/unchecks boxes the preview window updates to show the result of current choices
        self.ui.staticBackgroundBox.stateChanged.connect(
            lambda: self.preview_processing()
        )
        self.ui.dynamicBackgroundBox.stateChanged.connect(
            lambda: self.preview_processing()
        )
        self.ui.averageBox.stateChanged.connect(lambda: self.preview_processing())

    def close_dialog(self):
        """
        Method for closing the dialog window and delete the loaded preview

        TODO: With the latest changes of EBSP Indexer v0.1.0, this method should not be
        necessary anymore, and `self.reject()` should be connected to the
        `self.ui.buttonBox.rejected` signal instead
        """
        del self.s_preview
        gc.collect()
        self.reject()

    def setSavePath(self):
        """Sets the path for where the processed dataset should be saved"""
        if self.fileBrowser.getFile():
            self.save_path = self.fileBrowser.getPaths()[0]
            self.working_dir = os.path.dirname(self.save_path)
            self.ui.folderEdit.setText(self.working_dir)
            self.ui.filenameEdit.setText(os.path.basename(self.save_path))

    def setupInitialSettings(self):
        """
        Sets the avaialblity of processing by checking what processing
        that has already been done on the dataset, which depends on the
        naming of the dataset

        TODO: A more robust system to keep track of what processing has
        been done to a dataset
        """
        processing_steps = self.filenamebase.split("_")[1:]
        try:
            for step in processing_steps:
                if step == "sb":
                    self.already_indexed["sb"] = True
                    self.ui.staticBackgroundBox.setChecked(True)
                    self.ui.staticBackgroundBox.setEnabled(False)
                if step == "db":
                    self.already_indexed["db"] = True
                    self.ui.dynamicBackgroundBox.setChecked(True)
                    self.ui.dynamicBackgroundBox.setEnabled(False)
                if step == "anp":
                    self.already_indexed["anp"] = True
                    self.ui.averageBox.setChecked(True)
                    self.ui.averageBox.setEnabled(False)
        except:
            pass

        self.ui.buttonBox.button(QDialogButtonBox.Ok).setEnabled(False)

    def remove_static(self, dataset: EBSD, show_progressbar: Optional[bool] = True):
        """
        Removes the static backgorund from the dataset

        Parameters
        ----------
        dataset: EBSD
            The dataset that the processing is applied to
        show_progressbar: bool
            Whether progress bars should be displayed in the log
        """
        dataset.remove_static_background(show_progressbar=show_progressbar)

    def remove_dynamic(self, dataset:EBSD, show_progressbar:Optional[bool]=True):
        """
        Removes the dynamic backgorund from the dataset

        Parameters
        ----------
        dataset: EBSD
            The dataset that the processing is applied to
        show_progressbar: bool
            Whether progress bars should be displayed in the log
        """
        dataset.remove_dynamic_background(show_progressbar=show_progressbar)

    def average_neighbour(self, dataset: EBSD, show_progressbar:Optional[bool]=True):
        """
        Averages intensities within patterns by considering the pattern's 
        neighbohurs. 

        Parameters
        ----------
        dataset: EBSD
            The dataset that the processing is applied to
        show_progressbar: bool
            Whether progress bars should be displayed in the log
        """
        dataset.average_neighbour_patterns(
            self.gaussian_window, show_progressbar=show_progressbar
        )

    def showImage(self, dataset: LazyEBSD):
        """
        Updates the preview of the improved pattern
        
        Parameters
        ----------
        dataset: LazyEBSD
            The dataset that the processing is applied to
        """
        self.ui.previewWidget.vbl.setContentsMargins(0, 0, 0, 0)
        self.ui.previewWidget.canvas.ax.clear()
        self.ui.previewWidget.canvas.ax.axis(False)
        self.ui.previewWidget.canvas.ax.imshow(dataset.data, cmap="gray")
        self.ui.previewWidget.canvas.draw()

    def preview_processing(self):
        """
        Performs processing of the previewed pattern by considering
        what improvments that have been choosen
        """
        s_prev = self.s_preview.deepcopy().inav[0:3, 0:3]
        extensions = ""
        box_checked = False
        if self.ui.staticBackgroundBox.isChecked() and not self.already_indexed["sb"]:
            self.remove_static(dataset=s_prev, show_progressbar=False)
            extensions += "_sb"
            box_checked = True
        if self.ui.dynamicBackgroundBox.isChecked() and not self.already_indexed["db"]:
            self.remove_dynamic(dataset=s_prev, show_progressbar=False)
            extensions += "_db"
            box_checked = True
        if self.ui.averageBox.isChecked() and not self.already_indexed["anp"]:
            self.average_neighbour(dataset=s_prev, show_progressbar=False)
            extensions += "_anp"
            box_checked = True

        self.ui.buttonBox.button(QDialogButtonBox.Ok).setEnabled(box_checked)

        self.ui.filenameEdit.setText(f"{self.filenamebase}{extensions}.h5")

        self.showImage(s_prev.inav[1, 1])

        del s_prev

    def run_processing(self):
        """
        Displays a warning if static background noise has not been removed, 
        loads the dataset, and sends the 
        `scripts.pattern_processing.PatternProcessingDialog.apply_processing`
        method to the Job Manager
        """
        if not self.ui.staticBackgroundBox.isChecked():
            reply = QMessageBox(self).warning(
                self,
                "Processing Warning",
                "Removal of static background noise was not selected, which can produce unwanted results.\nAre you sure you want to continue? ",
                QMessageBox.Yes | QMessageBox.Abort,
                QMessageBox.Yes,
            )
            if reply != QMessageBox.Yes:
                return
        try:
            s: EBSD = kp.load(self.pattern_path, lazy=False)
        except Exception as e:
            raise e
        sendToJobManager(
            job_title=f"SN Improvement {self.pattern_name}",
            output_path=os.path.join(self.working_dir, self.ui.filenameEdit.text()),
            listview=self.parentWidget().ui.jobList,
            func=self.apply_processing,
            dataset=s,
        )

    def apply_processing(self, dataset: EBSD):
        """
        Applies processing to `dataset`
        
        Parameters
        ----------
        dataset: EBSD
            The dataset that the processing is applied to
        """
        if self.ui.staticBackgroundBox.isChecked() and not self.already_indexed["sb"]:
            print("Removing static background")
            self.remove_static(dataset=dataset)
        if self.ui.dynamicBackgroundBox.isChecked() and not self.already_indexed["db"]:
            print("Removing dynamic background")
            self.remove_dynamic(dataset=dataset)
        if self.ui.averageBox.isChecked() and not self.already_indexed["anp"]:
            print("Applying averaging")
            self.average_neighbour(dataset=dataset)

        self.save_path = os.path.join(
            self.working_dir, self.ui.filenameEdit.text()
        )  # Get current save path
        try:
            dataset.save(
                self.save_path,
                overwrite=True,
            )
            print(f"Processed dataset saved as {self.ui.filenameEdit.text()}")
            del dataset
            gc.collect()
        except Exception as e:
            print(f"Could not save processed pattern: {e}")
            del dataset
            gc.collect()
            self.reject()
