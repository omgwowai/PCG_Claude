import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # Tools/weather
REPO = os.path.dirname(os.path.dirname(HERE))
for p in (HERE, os.path.join(REPO, "Content", "Python")):            # weather_lab's pure helpers (Task 17)
    if p not in sys.path:
        sys.path.insert(0, p)
