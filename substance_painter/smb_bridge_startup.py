import sys
import os

startup_dir = os.path.dirname(os.path.realpath(__file__))
if startup_dir not in sys.path:
    sys.path.append(startup_dir)

from smb_bridge import pipeline

def start_plugin():
    pipeline.start_plugin()

def close_plugin():
    pipeline.close_plugin()