from fastapi import FastAPI

from app.api import router


def test_api_router_generates_openapi_contract():
    app = FastAPI()
    app.include_router(router, prefix="/api")

    schema = app.openapi()

    assert schema["openapi"].startswith("3.")
    assert "/api/tasks/{task_id}/modify" in schema["paths"]
    modify = schema["paths"]["/api/tasks/{task_id}/modify"]["post"]
    assert modify["requestBody"]["required"] is True
