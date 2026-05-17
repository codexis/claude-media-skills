import sys
from pathlib import Path

# Make scripts/src/ importable from tests/
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))