import sys
import os

print()

if sys.platform == "darwin":
    DISKS = [f"{os.path.dirname(os.path.abspath(__file__))}/files", ]

elif sys.platform.startswith("win"):
    DISKS = [""]