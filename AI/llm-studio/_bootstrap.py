"""Tiny shim so each Streamlit page can `from shared.* import ...`."""
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

# Local data dir for uploads / outputs / user skills / endpoints. .gitignored.
DATA_DIR = Path(__file__).resolve().parent / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
OUTPUTS_DIR = DATA_DIR / "outputs"
SKILLS_DIR = DATA_DIR / "skills"
ENDPOINTS_FILE = DATA_DIR / "endpoints.json"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
SKILLS_DIR.mkdir(parents=True, exist_ok=True)

# Wire singletons so pages can `from shared.skills import get_registry; get_registry()` without args.
from shared.skills.registry import get_registry as _get_skill_registry  # noqa: E402
from shared.llm.endpoints import get_endpoints as _get_endpoints  # noqa: E402

_get_skill_registry(SKILLS_DIR)
_get_endpoints(ENDPOINTS_FILE)
