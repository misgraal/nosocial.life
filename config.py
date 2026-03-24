import sys
import os

if sys.platform == "darwin":
    DISKS = [f"{os.path.dirname(os.path.abspath(__file__))}/files", f"{os.path.dirname(os.path.abspath(__file__))}/files2"]
    system = "darwin"

elif sys.platform.startswith("win"):
    DISKS = ["H:\\", "I:\\"]
    system = "win"