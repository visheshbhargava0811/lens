from fastapi import APIRouter

from lens import __version__
from lens.core.settings import get_settings
from lens.schemas.common import Health

router = APIRouter(tags=["health"])


@router.get("/health", response_model=Health)
def health() -> Health:
    """Liveness only. Does not check downstream services. Deployed: no version or environment (ADR-0042)."""
    s = get_settings()
    return Health() if s.deployed else Health(version=__version__, env=s.app_env)
