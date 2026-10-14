import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
for p in (os.path.join(REPO, "Content", "Python"), os.path.join(REPO, "Tools", "pypcg")):
    if p not in sys.path:
        sys.path.insert(0, p)
