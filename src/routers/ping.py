from fastapi import APIRouter
# from sqlalchemy import text

from ..dependencies import DatabaseDep, SettingsDep
from ..exceptions import OllamaConnectionError, OllamaException, OllamaTimeoutError
from ..schemas.api.health import HealthResponse, ServiceStatus
from ..services.ollama import OllamaClient

router = APIRouter()


@router.get("/ping", tags=["Health"])
async def ping():
    """Simple ping endpoint for basic connectivity tests."""
    return {"status": "ok", "message": "pong"}


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Check the health and status of the API service including database connectivity.",
    response_description="Service health information",
    tags=["Health"],
)
async def health_check(settings: SettingsDep, database: DatabaseDep) -> HealthResponse:
    """
    Comprehensive health check endpoint for monitoring and load balancer probes.

    This endpoint provides information about the service health, version,
    environment, and checks connectivity to dependent services like database.

    Returns:
        HealthResponse: Contains service status, version, environment, and service checks

    Example:
        Response:
        ```
        {
            "status": "ok",
            "version": "0.1.0",
            "environment": "development",
            "service_name": "rag-api",
            "services": {
                "database": {"status": "healthy", "message": "Connected successfully"}
            }
        }
        ```
    """
    services = {}
    overall_status = "ok"

    # Test database connectivity
    try:
        with database.get_session() as session:
            # Simple query to test connection
            session.execute(text("SELECT 1"))
            services["database"] = ServiceStatus(
                status="healthy", message="Connected successfully")
    except Exception as e:
        services["database"] = ServiceStatus(
            status="unhealthy", message=f"Connection failed: {str(e)}")
        overall_status = "degraded"

    # Test Ollama service connectivity (Week 1 notebook requirement)
    try:
        ollama_client = OllamaClient(settings)
        ollama_health = await ollama_client.health_check()
        services["ollama"] = ServiceStatus(
            status=ollama_health["status"], message=ollama_health["message"])
        if ollama_health["status"] != "healthy":
            overall_status = "degraded"
    except OllamaConnectionError as e:
        services["ollama"] = ServiceStatus(
            status="unhealthy", message=f"Cannot connect to Ollama: {str(e)}")
        overall_status = "degraded"
    except OllamaTimeoutError as e:
        services["ollama"] = ServiceStatus(
            status="unhealthy", message=f"Ollama timeout: {str(e)}")
        overall_status = "degraded"
    except OllamaException as e:
        services["ollama"] = ServiceStatus(
            status="unhealthy", message=f"Ollama error: {str(e)}")
        overall_status = "degraded"
    except Exception as e:
        services["ollama"] = ServiceStatus(
            status="unhealthy", message=f"Unexpected Ollama error: {str(e)}")
        overall_status = "degraded"

    return HealthResponse(
        status=overall_status,
        version=settings.app_version,
        environment=settings.environment,
        service_name=settings.service_name,
        services=services,
    )
