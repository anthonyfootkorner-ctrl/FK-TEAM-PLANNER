import sys
from pathlib import Path

# rend le package stockflow importable depuis les tests
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
