from os import path
from kikuchipy import load
from PySide6.QtWidgets import QDialog

from utils.filebrowser import FileBrowser
from ui.ui_roi_dialog import Ui_ROIDialog


class RegionOfInteresDialog(QDialog):
    def __init__(
        self,
        pattern_path=None,
    ):
        super().__init__()

        self.working_dir = path.dirname(pattern_path)

        if pattern_path == None:
            self.filenamebase = "Pattern"
            self.pattern_path = path.join(self.working_dir, "Pattern.dat")

        else:
            self.pattern_path = pattern_path
            
        self.filenamebase = path.basename(self.pattern_path).split(".")[0]

        # Standard filename of processed pattern
        self.save_path = path.join(self.working_dir, f"{self.filenamebase}_ROI_x0_x1_y0_y1.h5")

        self.ui = Ui_ROIDialog()
        self.ui.setupUi(self)
        self.setWindowTitle(f"{self.windowTitle()} - {self.pattern_path}")
        self.setupConnections()

        try:
            self.s = load(self.pattern_path, lazy=True)
        except Exception as e:
            raise e

        self.fileBrowser = FileBrowser(
            mode=FileBrowser.SaveFile,
            dirpath=self.working_dir,
            filter_name="Hierarchical Data Format (*.h5);;NordifUF Pattern Files (*.dat)",
        )

    def setSavePath(self):
        if self.fileBrowser.getFile():
            self.save_path = self.fileBrowser.getPaths()[0]
            self.ui.pathLineEdit.setText(self.save_path)

    def updateSavePath(self):
        self.options = self.getOptions()
        x_start = self.options["x-start"]
        x_end = self.options["x-end"]
        y_start = self.options["y-start"]
        y_end = self.options["y-end"]

        self.save_path = path.join(self.working_dir, f"{self.filenamebase}_{x_start}_{x_end}_{y_start}_{y_end}.h5")
        self.ui.pathLineEdit.setText(self.save_path)

    def setupConnections(self):
        self.ui.browseButton.clicked.connect(lambda: self.setSavePath())
        self.ui.buttonBox.accepted.connect(lambda: self.run_roi_selection())
        self.ui.buttonBox.rejected.connect(lambda: self.reject())
        self.ui.pathLineEdit.setText(self.save_path)
        self.ui.lineEditXstart.textChanged.connect(lambda: self.updateSavePath())
        self.ui.lineEditXend.textChanged.connect(lambda: self.updateSavePath())
        self.ui.lineEditYstart.textChanged.connect(lambda: self.updateSavePath()) 
        self.ui.lineEditYend.textChanged.connect(lambda: self.updateSavePath())

    def getOptions(self) -> dict:
        return {
            "x-start": int(self.ui.lineEditXstart.text()),
            "x-end": int(self.ui.lineEditXend.text()),
            "y-start": int(self.ui.lineEditYstart.text()),
            "y-end": int(self.ui.lineEditYend.text()),
        }

    def run_roi_selection(self):
        self.options = self.getOptions()
        x_start = self.options["x-start"]
        x_end = self.options["x-end"]
        y_start = self.options["y-start"]
        y_end = self.options["y-end"]
        print(x_start, x_end, y_start, y_end)
        self.s2 = self.s.inav[x_start:x_end, y_start:y_end]
        try:
            filepath = self.ui.pathLineEdit.text()

            print(filepath)
            self.s2.save(
                filepath,
                overwrite=True,
            )
            print("Processing complete")
            self.accept()
        except Exception as e:
            print(f"Could not save processed pattern: {e}")
            self.reject()