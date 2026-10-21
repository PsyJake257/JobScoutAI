import os
import sys

if getattr(sys, "frozen", False):
    basis = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    os.environ.setdefault("TCL_LIBRARY", os.path.join(basis, "_tcl_data"))
    os.environ.setdefault("TK_LIBRARY", os.path.join(basis, "_tk_data"))
