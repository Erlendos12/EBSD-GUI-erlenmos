"""Utility for redirecting standard output from a thread through signals"""
import PySide6.QtCore as QtCore

class ThreadedOutput(QtCore.QObject):
    """QObject to be used in redirecting standard output from a thread through signals"""

    outputLine = QtCore.Signal(str)
    outputError = QtCore.Signal(str)

    def __init__(self) -> None:
        """
        QObject to be used in redirecting standard output from a thread through signals
        
        Attributes
        ----------
        outputLine: Signal[str]
            Emits the captured standard output as a string 
        outputError: Signal[str]
            Emits the fully traced error as a string 
        """
        super().__init__()

    def flush(self):
        """Dummy function to allow reciving of progressbars from kikuchipy"""
        pass

    def write(self, line: str) -> None:
        """Capture stdout and emit signal"""
        self.outputLine.emit(line)

    def errorwrite(self, line: str) -> None:
        """Capture stderr and emit signal"""
        self.outputError.emit(line)
