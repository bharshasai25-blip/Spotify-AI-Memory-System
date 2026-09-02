from .auth import router as auth_router
from .health import router as health_router
from .events import router as events_router
from .chat import router as chat_router
from .memory_control import router as memory_control_router
from .memory_correction import router as memory_correction_router
from .memory_deletion import router as memory_deletion_router
from .memory_search import router as memory_search_router
from .memory_preference import router as memory_preference_router
from .memory_explaination import router as memory_explaination_router
__all__=[
    "auth_router",
    "health_router",
    "events_router",
    "chat_router",
    "memory_control_router",
    "memory_correction_router",
    "memory_deletion_router",
    "memory_search_router",
    "memory_preference_router",
    "memory_explaination_router"
]