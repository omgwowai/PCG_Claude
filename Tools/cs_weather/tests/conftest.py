import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
for p in (os.path.join(ROOT, "Content", "Python"), os.path.join(ROOT, "Tools", "cs_weather")):
    if p not in sys.path:
        sys.path.insert(0, p)
