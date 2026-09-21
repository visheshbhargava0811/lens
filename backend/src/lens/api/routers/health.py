from fastapi import APIRouter

from lens import __version__
from lens.core.settings import get_settings
from lens.schemas.common import Health

router = APIRouter(tags=["health"])


@router.get("/health", response_model=Health)
def health() -> Health:
    """Liveness only. Does not check downstream services."""
    return Health(version=__version__, env=get_settings().app_env)
