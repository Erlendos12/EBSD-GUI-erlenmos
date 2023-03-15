from os import path
from datetime import date
from typing import Optional, Sequence
import json
import warnings

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QDialogButtonBox, QMainWindow, QTableWidgetItem
import kikuchipy as kp
from kikuchipy.signals.ebsd import EBSD, LazyEBSD
from kikuchipy.signals.ebsd_master_pattern import (
    LazyEBSDMasterPattern,
)
from kikuchipy.indexing._merge_crystal_maps import merge_crystal_maps
import matplotlib.pyplot as plt
import matplotlib as mpl
import numpy as np

from orix import io, plot
from orix.crystal_map import CrystalMap, PhaseList
from orix.vector import Vector3d

from utils import (
    SettingFile,
    FileBrowser,
    sendToJobManager,
    get_setting_file_bottom_top,
)
from ui.ui_refine_setup import Ui_RefineSetupDialog

# Ignore warnings to avoid crash with integrated console
warnings.filterwarnings("ignore")


class RefineSetupDialog(QDialog):
    def __init__(self, parent: QMainWindow, file_path: Optional[str] = ""):
        super().__init__(parent)

        parameter_file, self.xmap_dir = get_setting_file_bottom_top(
            file_path, "indexing_parameters.txt", return_dir_path=True
        )
        self.setting_file, self.working_dir = get_setting_file_bottom_top(
            file_path, "project_settings.txt", return_dir_path=True
        )
        self.program_settings = SettingFile("advanced_settings.txt")
        # if self.xmap_dir is None:
        #     self.xmap_dir = path.dirname(file_path)
        self.pattern_path = ""
        self.xmap_path = ""
        self.ui = Ui_RefineSetupDialog()
        self.ui.setupUi(self)
        self.setWindowTitle(f"{self.windowTitle()} - {file_path}")
        self.fileBrowserOF = FileBrowser(
            mode=FileBrowser.OpenFile, filter_name="Hierarchical Data Format (*.h5);"
        )
        self.fileBrowserOF.setDefaultDir(self.working_dir)
        # Load file
        try:
            try:
                s_prew = kp.load(file_path, lazy=True)
                if isinstance(s_prew, (EBSD, LazyEBSD)):
                    self.pattern_path = file_path
            except:
                xmap = io.load(file_path)
                if isinstance(xmap, (CrystalMap)):
                    self.xmap_path = file_path
                    if parameter_file is None:
                        print(
                            "No indexing parameters associated with selected crystal map"
                        )
                        raise Exception
                    self.pattern_path = path.join(self.working_dir,parameter_file.read("Pattern name"))
                    self.load_crystal_map(self.xmap_path)
                    try:
                        s_prew = kp.load(self.pattern_path)
                    except Exception as e:
                        print("Could not load patterns associated with crystal map")
                        raise e
        except Exception as e:
            raise e
        self.ui.labelNavigationShape.setText(
            f"Navigation shape: {str(s_prew.axes_manager.navigation_shape[::-1])}"
        )
        self.binnings = self.getBinningShapes(s_prew)
        self.mp_paths = {}
        self.phases = PhaseList()
        self.colors = [
            "blue",
            "orange",
            "lime",
            "yellow",
        ]

        self.setupConnections()
        self.load_parameters()
        self.setAvailableButtons()

        # Matplotlib configuration
        mpl.use("agg")
        plt.rcParams.update({"font.size": 20})
        self.savefig_kwds = dict(pad_inches=0, bbox_inches="tight", dpi=150)

    def setupConnections(self):
        self.ui.buttonBox.accepted.connect(lambda: self.run_refinement())
        self.ui.buttonBox.rejected.connect(lambda: self.reject())
        self.ui.pushButtonLoadMP.clicked.connect(lambda: self.load_master_pattern())
        self.ui.pushButtonRemoveMP.clicked.connect(lambda: self.remove_master_pattern())
        self.ui.pushButtonLoadXmap.clicked.connect(lambda: self.load_crystal_map())
        self.ui.comboBoxBinning.currentTextChanged.connect(
            lambda: self.ui.labelSignalShape.setText(
                f"Signal Shape: {self.binnings[self.ui.comboBoxBinning.currentText()]}"
            )
        )
        self.ui.comboBoxBinning.addItems(self.binnings.keys())
        self.ui.labelSignalPath.setText(self.pattern_path)

    def getOptions(self) -> dict:
        return {
            "mask": self.ui.checkBoxMask.isChecked(),
            "binning": self.ui.comboBoxBinning.currentText(),
            "lazy": self.ui.checkBoxLazy.isChecked(),
            "ncc": [
                self.ui.checkBoxNCC.isChecked(),
                self.save_ncc_map,
            ],
            "phase": [self.ui.checkBoxPhase.isChecked(), self.save_phase_map],
            "orientation": [
                self.ui.checkBoxOrientation.isChecked(),
                self.save_ipf_map,
            ],
            "ckey_direction": self.ui.lineEditColorKey.text(),
            "convention": self.ui.comboBoxConvention.currentText().lower(),
            "pc": (
                self.ui.patternCenterX.value(),
                self.ui.patternCenterY.value(),
                self.ui.patternCenterZ.value(),
            ),
            "method": self.ui.comboBoxMethod.currentText(),
            "ref_kwargs": self.ui.lineEditRefKwargs.text(),
        }

    def load_parameters(self):
        # read current setting from project_settings.txt, advanced_settings.txt
        try:
            convention = self.setting_file.read("Convention")
        except:
            convention = self.program_settings.read("Convention")
        self.ui.comboBoxConvention.setCurrentText(convention)
        try:
            self.ui.patternCenterX.setValue(float(self.setting_file.read("X star")))
            self.ui.patternCenterY.setValue(float(self.setting_file.read("Y star")))
            self.ui.patternCenterZ.setValue(float(self.setting_file.read("Z star")))
        except:
            self.pc = np.array([0.500, 0.200, 0.500])
        try:
            self.colors = json.loads(self.program_settings.read("Colors"))
        except:
            pass
        try:
            if self.program_settings.read("Lazy Loading") == "False":
                self.ui.checkBoxLazy.setChecked(False)
        except:
            pass

        binningBox = self.ui.comboBoxBinning
        try:
            binning = json.loads(self.setting_file.read("Binning"))
            binningBox.setCurrentIndex(binningBox.findText(str(binning)))
        except:
            binningBox.setCurrentIndex(binningBox.findText("None"))

        i = 1
        while True:
            try:
                mp_path = self.setting_file.read(f"Master pattern {i}")
                self.load_master_pattern(mp_path)
                i += 1
            except:
                break

    # TODO Make a refine_parameters text document
    # def save_parameters(self):
    #     self.setting_file.delete_all_entries()  # Clean up initial dictionary
    #     options = self.getOptions()
    #     for idx, mp_path in enumerate(self.mp_paths):
    #         self.setting_file.write(
    #             f"Master pattern {idx}", mp_path
    #         )
    #     self.setting_file.write("Convention", options["convention"].upper())
    #     pc = options["pc"]
    #     self.setting_file.write("X star", pc[0])
    #     self.setting_file.write("Y star", pc[1])
    #     self.setting_file.write("Z star", pc[2])
    #     self.setting_file.write("Binning", options["binning"])
    #     self.setting_file.save()

    def load_crystal_map(self, xmap_path: Optional[str] = None):
        if xmap_path is not None:
            self.xmap_path = xmap_path
            self.xmap_name = path.basename(self.xmap_path)
            self.xmap_dir = path.dirname(self.xmap_path)
            xmap = io.load(xmap_path)
            self.updateCrystalMapTable(xmap)
        elif self.fileBrowserOF.getFile():
            self.xmap_path = self.fileBrowserOF.getPaths()[0]
            self.xmap_name = path.basename(self.xmap_path)
            self.xmap_dir = path.dirname(self.xmap_path)
            xmap = io.load(self.xmap_path)
            self.updateCrystalMapTable(xmap)

    def load_master_pattern(self, mp_path: Optional[str] = None):
        if mp_path is not None:
            try:
                mp: LazyEBSDMasterPattern = kp.load(mp_path, lazy=True)
                if mp.phase.name == "":
                    mp.phase.name = path.dirname(mp_path).split("/").pop()
                self.phases.add(mp.phase)
                mp.phase.color = self.colors[len(self.phases.ids) - 1]
                self.mp_paths[mp.phase.name] = mp_path
            except Exception as e:
                print("Phase could not be loaded from master pattern", e)
            self.updatePhaseTable()
        elif self.fileBrowserOF.getFile():
            mp_paths = self.fileBrowserOF.getPaths()
            for mp_path in mp_paths:
                try:
                    mp: LazyEBSDMasterPattern = kp.load(mp_path, lazy=True)
                    if mp.phase.name == "":
                        mp.phase.name = path.dirname(mp_path).split("/").pop()
                    self.phases.add(mp.phase)
                    mp.phase.color = self.colors[len(self.phases.ids) - 1]
                    self.mp_paths[mp.phase.name] = mp_path
                except Exception as e:
                    print("Phase could not be loaded from master pattern", e)
            self.updatePhaseTable()

    def updatePhaseTable(self):
        """
        NAME_COL = 0
        NUMBER_COL = 1
        ISS_COL = 2
        CRYSTAL_COL = 3
        COLOR_COL = 4
        """
        phasesTable = self.ui.tableWidgetPhase
        phasesTable.setRowCount(len(self.phases.ids))
        row = 0
        for _, phase in self.phases:
            sg = phase.space_group
            entries = [
                phase.name,
                sg.number,
                sg.short_name,
                sg.crystal_system,
                phase.color,
            ]
            for col, entry in enumerate(entries):
                item = QTableWidgetItem(str(entry))
                item.setFlags(item.flags() ^ Qt.ItemIsEditable)
                phasesTable.setItem(row, col, item)
            row += 1
        self.setAvailableButtons()

    def updateCrystalMapTable(self, xmap: CrystalMap):
        self.ui.labelXmapPath.setText(self.xmap_path)
        xmapTable = self.ui.tableWidgetXmap
        xmapTable.setRowCount(len(xmap.phases.ids))
        xmapTable.setVerticalHeaderLabels(
            [f"P{i}" for i in range(len(xmap.phases.ids))]
        )
        row = 0
        for _, phase in xmap.phases:
            phase_amount = xmap[f"{phase.name}"].size / xmap.size
            entries = [phase.name, f"{xmap[f'{phase.name}'].size} ({phase_amount:.1%})"]
            for col, entry in enumerate(entries):
                item = QTableWidgetItem(str(entry))
                item.setFlags(item.flags() ^ Qt.ItemIsEditable)
                xmapTable.setItem(row, col, item)
            row += 1
        self.setAvailableButtons()

    def remove_master_pattern(self):
        phaseTable = self.ui.tableWidgetPhase
        indexes = phaseTable.selectionModel().selectedRows()
        countRow = len(indexes)
        for i in range(countRow, 0, -1):
            phase_key = phaseTable.item(indexes[i - 1].row(), 0).text()
            self.phases.__delitem__(phase_key)
            if phase_key in self.mp_paths.keys():
                self.mp_paths.pop(phase_key)
            phaseTable.removeRow(indexes[i - 1].row())
        self.setAvailableButtons()

    def setAvailableButtons(self):
        ok_flag = False
        phase_map_flag = False
        add_phase_flag = True
        xmap_flag = False
        n_phases = self.ui.tableWidgetPhase.rowCount()
        n_xmap = self.ui.tableWidgetXmap.rowCount()
        if n_phases:
            ok_flag = True
            if n_phases > 1:
                phase_map_flag = True
        if n_xmap:
            xmap_flag = True
        self.ui.buttonBox.button(QDialogButtonBox.Ok).setEnabled(ok_flag and xmap_flag)
        self.ui.checkBoxPhase.setEnabled(phase_map_flag)
        self.ui.checkBoxPhase.setChecked(phase_map_flag)
        self.ui.pushButtonLoadMP.setEnabled(add_phase_flag)

    def getBinningShapes(self, signal: LazyEBSD) -> dict:
        sig_shape = signal.axes_manager.signal_shape[::-1]
        binnings: dict = {"None": sig_shape}
        for num in range(2, 17):
            if sig_shape[0] % num == 0 and sig_shape[1] % num == 0:
                binnings[f"{num}"] = (int(sig_shape[0] / num), int(sig_shape[1] / num))
        return binnings

    def refine_orientations(self, s: EBSD, xmap: CrystalMap, master_patterns: dict, options: dict):
        options = self.getOptions()
        binning = eval(options["binning"])
        pc = options["pc"]
        convention = options["convention"]
        mask = options["mask"]
        method = options["method"]
        if len(options["ref_kwargs"]):
            ref_kwargs = eval(options["ref_kwargs"])
        else:
            ref_kwargs = {}
        # self.save_parameters()
        # print(f"Loading {self.pattern_path} | lazy = {lazy}")
        # try:
        #     s: EBSD = kp.load(self.pattern_path, lazy=lazy)
        # except Exception as e:
        #     raise e
        # try:
        #     xmap: CrystalMap = io.load(self.xmap_path)
        # except Exception as e:
        #     raise e
        energy: int = s.metadata.Acquisition_instrument.SEM.beam_energy
        nav_shape = s.axes_manager.navigation_shape[::-1]
        if binning is None:
            binning = 1
        else:
            s = s.rebin(
                new_shape=s.axes_manager.navigation_shape + self.binnings[str(binning)]
            )
        sig_shape = s.axes_manager.signal_shape[::-1]  # (Rows, columns)
        det = kp.detectors.EBSDDetector(
            shape=sig_shape,
            binning=binning,
            sample_tilt=s.detector.sample_tilt,
            tilt=s.detector.tilt,
            pc=pc,
            convention=convention,
        )
        if mask:
            signal_mask = ~kp.filters.Window("circular", det.shape).astype(bool)
        else:
            signal_mask = None
        print("------- Detector stats -------")
        print(f"Navigation shape: {nav_shape}")
        print(f"Signal shape: {sig_shape}")
        print(f"Signal mask: {mask}")
        print(f"PC convention: {convention}")
        ref_xmaps = {}
        for mp_key, mp in master_patterns.items():
            mp.phase.color = self.colors[xmap.phases.id_from_name(mp_key)]
            print(f"\nRefining with Master Pattern: {mp.phase.name}")
            nav_mask_phase = ~(xmap.phase_id == xmap.phases.id_from_name(mp_key))
            nav_mask_phase = nav_mask_phase.reshape(xmap.shape)
            ref_xmaps[mp_key] = s.refine_orientation(
                xmap=xmap,
                detector=det,
                master_pattern=mp,
                energy=energy,
                navigation_mask=nav_mask_phase,
                signal_mask=signal_mask,
                trust_region=[1, 1, 1],
                method=method,
                method_kwargs=ref_kwargs,
                compute=True,
            )
        ref_xmaps_list = list(ref_xmaps.values())
        # nav_mask_list = []
        # for _ in ref_xmaps_list:
        #         nav_mask_list.append(None)
        # if not xmap.all_indexed:
        #     nav_mask_not_indexed = xmap.is_indexed.reshape(xmap.shape)
        #     nav_mask_list.append(nav_mask_not_indexed)
        #     ref_xmaps_list.append(xmap)
        # print("nav_mask_list len",len(nav_mask_list))
        # print(ref_xmaps_list)
        if len(ref_xmaps_list) == 1:
            ref_xmap = ref_xmaps_list[0]
        else:
            ref_xmap = merge_crystal_maps(ref_xmaps_list)
        # ref_xmap.phases.add_not_indexed()
        # if not xmap.all_indexed:
        #     print(xmap.shape)
        #     for x in range(xmap.shape[0]):
        #         for y in range(xmap.shape[1]):
        #             if not xmap[x,y].is_indexed.any():
        #                 print("Adding not indexed")
        #                 ref_xmap[x,y].phase_id = -1
        # print("xmap:",ref_xmap)
        # print("xmap_phases",ref_xmap.phases)
        # print("phases_in_data",ref_xmap.phases_in_data)
        io.save(
            path.join(
                self.xmap_dir, f"refined_{path.splitext(self.xmap_name)[0]}.h5"
            ),
            ref_xmap,
        )
        io.save(
            path.join(
                self.xmap_dir, f"refined_{path.splitext(self.xmap_name)[0]}.ang"
            ),
            ref_xmap,
        )
        print("Result was saved as ref_xmap_hi.ang and ref_xmap_hi.h5")

        for key in ["phase", "orientation", "ncc"]:
            optionEnabled, optionExecute = options.get(key)
            if optionEnabled:
                try:
                    if key == "orientation":
                        optionExecute(ref_xmap, eval(f"[{options['ckey_direction']}]"))
                    else:
                        optionExecute(ref_xmap)
                except Exception as e:
                    print(f"Could not save {key}_map:\n{e}")
        print(f"Finished refining orientations for {self.xmap_name}")

    def run_refinement(self):
        options = self.getOptions()
        try:
            s: EBSD = kp.load(self.pattern_path, lazy=options['lazy'])
        except Exception as e:
            raise e
        try:
            xmap: CrystalMap = io.load(self.xmap_path)
        except Exception as e:
            raise e
        energy: int = s.metadata.Acquisition_instrument.SEM.beam_energy
        master_patterns = {}
        for mp_key, mp_path in self.mp_paths.items():
            mp = kp.load(
                mp_path,
                energy=energy,
                projection="lambert",
                hemisphere="upper",
                lazy=options["lazy"],
            )
            if mp.phase.name == "":  # If the master pattern is missing the name of the phase
                mp.phase.name = path.dirname(mp_path).split("/").pop()
            master_patterns[mp_key] = mp
        sendToJobManager(
            job_title=f"Refine orientations {self.xmap_name}",
            output_path=self.xmap_dir,
            listview=self.parentWidget().ui.jobList,
            func=self.refine_orientations,
            allow_cleanup=False,
            allow_logging=False,
            s=s,
            xmap=xmap,
            master_patterns=master_patterns,
            options=options
        )

    def save_quality_metrics(self, xmap):
        """
        Save plots of quality metrics
        """
        print("Saving quality metric for combined map ...")
        aspect_ratio = xmap.shape[1] / xmap.shape[0]
        figsize = (8 * aspect_ratio, 4.5 * aspect_ratio)
        fig, ax = plt.subplots(nrows=2, ncols=2, figsize=figsize)
        for a, to_plot in zip(ax.ravel(), ["pq", "cm", "fit", "nmatch"]):
            arr = xmap.get_map_data(to_plot)
            im = a.imshow(arr)
            fig.colorbar(im, ax=a, label=to_plot)
            a.axis("off")
            plt.imsave(
                path.join(self.xmap_dir, f"quality_metrics_{to_plot}.png"),
                arr,
            )
        fig.subplots_adjust(wspace=0, hspace=0.05)
        fig.savefig(
            path.join(self.xmap_dir, "quality_metrics_all.png"), **self.savefig_kwds
        )

    def save_phase_map(self, xmap):
        """
        Plot phase map
        """
        print("Saving phase map ...")
        fig = xmap.plot(return_figure=True, remove_padding=True)
        fig.savefig(
            path.join(self.xmap_dir, "refined_phase_map.png"), **self.savefig_kwds
        )

    def save_ipf_map(
        self,
        xmap: CrystalMap,
        ckey_direction: Optional[Sequence] = [0, 0, 1],
        ckey_overlay: Optional[bool] = False,
    ):
        """
        Plot inverse pole figure map with orientation colour key

        Parameters
        ----------
        xmap : CrystalMap
            The crystal map which the orientations originates from
        ckey_direction: sequence
            3D vector used to determine the orientation color key
        ckey_overlay : bool
            Whether the colour orientation key is shown on top of the map or saved to seperate png, default is seperate
        """
        print("Saving inverse pole figure map ...")
        v_ipf = Vector3d(ckey_direction)
        sym = xmap.phases[0].point_group
        ckey = plot.IPFColorKeyTSL(sym, v_ipf)
        print(ckey)
        fig_ckey = ckey.plot(return_figure=True)
        rgb_direction = ckey.orientation2color(xmap.rotations)
        fig = xmap.plot(rgb_direction, remove_padding=True, return_figure=True)
        if ckey_overlay:
            ax_ckey = fig.add_axes(
                [0.77, 0.07, 0.2, 0.2], projection="ipf", symmetry=sym
            )
            ax_ckey.plot_ipf_color_key(show_title=False)
            ax_ckey.patch.set_facecolor("None")
        else:
            fig_ckey.savefig(
                path.join(self.xmap_dir, "orientation_colour_key.png"),
                **self.savefig_kwds,
            )
        fig.savefig(path.join(self.xmap_dir, "refined_IPF.png"), **self.savefig_kwds)

    def save_ncc_map(self, xmap: CrystalMap):
        if len(xmap.phases.ids) == 1:
            fig = xmap.plot(
                "scores",
                return_figure=True,
                colorbar=True,
                colorbar_label="NCC",
                cmap="gray",
                remove_padding=True,
            )
        else:
            fig = xmap.plot(
                value=xmap.merged_scores[:, 0],
                colorbar=True,
                colorbar_label="NCC",
                return_figure=True,
                cmap="gray",
                remove_padding=True
            )
        fig.savefig(
            path.join(self.xmap_dir, "refined_NCC.png"),
            **self.savefig_kwds,
        )


# TODO Add more Hough related properties, better way to sort?
def log_hi_parameters(
    dir_out: str,
    signal: EBSD | LazyEBSD = None,
    xmap: CrystalMap = None,
    mp_paths: dict = None,
    pattern_center: np.ndarray = None,
    convention: str = "BRUKER",
    binning: int = 1,
):
    """
    Assumes convention is BRUKER for pattern center if none is given
    """

    log = SettingFile(path.join(dir_out, "hi_parameters.txt"))
    K = ["strs"]
    ### Time and date
    log.write("Date", f"{date.today()}\n")

    ### SEM parameters
    log.write("Microscope", signal.metadata.Acquisition_instrument.SEM.microscope)
    log.write(
        "Acceleration voltage",
        f"{signal.metadata.Acquisition_instrument.SEM.beam_energy} kV",
    )
    log.write("Sample tilt", f"{signal.detector.sample_tilt} degrees")
    log.write("Camera tilt", f"{signal.detector.tilt} degrees")
    log.write(
        "Working distance",
        signal.metadata.Acquisition_instrument.SEM.working_distance,
    )
    log.write("Magnification", signal.metadata.Acquisition_instrument.SEM.magnification)
    log.write(
        "Navigation shape (rows, columns)",
        signal.axes_manager.navigation_shape[::-1],
    )
    if binning == 1:
        log.write("Binning", None)
    else:
        log.write("Binning", binning)
    log.write("Signal shape (rows, columns)", signal.axes_manager.signal_shape[::-1])
    log.write("Step size", f"{signal.axes_manager[0].scale} um\n")

    ### HI parameteres

    log.write("kikuchipy version", kp.__version__)

    if mp_paths is not None:
        for i, mp_path in enumerate(mp_paths.values(), 1):
            log.write(f"Master pattern path {i}", mp_path)
    log.write("PC convention", f"{convention.upper()}")
    log.write("Pattern center (x*, y*, z*)", f"{pattern_center}")

    if len(xmap.phases.names) > 1:
        for i, ph in enumerate(xmap.phases.names, 1):
            phase_amount = xmap[f"{ph}"].size / xmap.size
            log.write(
                f"Phase {i}: {ph} [% ( # points)] ",
                f"{phase_amount:.1%}, ({xmap[f'{ph}'].size})",
            )

        not_indexed_percent = xmap["not_indexed"].size / xmap.size
        log.write(
            "Not indexed", f"{xmap['not_indexed'].size} ({not_indexed_percent:.1%})"
        )

    log.save()
