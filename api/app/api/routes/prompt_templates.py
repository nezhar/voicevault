from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, is_admin_user, require_admin
from app.db.database import get_db
from app.models.user import User
from app.models.schemas import (
    PromptTemplateCreate,
    PromptTemplateResponse,
    PromptTemplateUpdate,
)
from app.services.prompt_template_service import PromptTemplateService

router = APIRouter()


@router.get("/", response_model=list[PromptTemplateResponse])
async def list_prompt_templates(
    active_only: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Every authenticated user may read the templates the chat offers.

    Inactive templates are drafts that only the configurator shows, so the
    active_only flag is honoured for admins alone; everyone else always gets
    the active set.
    """

    if not is_admin_user(current_user):
        active_only = True

    service = PromptTemplateService(db)
    return service.list_templates(active_only=active_only)


@router.post("/", response_model=PromptTemplateResponse)
async def create_prompt_template(
    template_data: PromptTemplateCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Admin only: templates are org-wide configuration, not personal data."""

    service = PromptTemplateService(db)
    template = service.create_template(**template_data.dict())
    return template


@router.put("/{template_id}", response_model=PromptTemplateResponse)
async def update_prompt_template(
    template_id: UUID,
    template_data: PromptTemplateUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Admin only."""

    service = PromptTemplateService(db)
    update_data = template_data.dict(exclude_unset=True)
    template = service.update_template(template_id, **update_data)

    if not template:
        raise HTTPException(status_code=404, detail="Prompt template not found")

    return template


@router.delete("/{template_id}")
async def delete_prompt_template(
    template_id: UUID,
    db: Session = Depends(get_db),
    _admin: User = Depends(require_admin),
):
    """Admin only."""

    service = PromptTemplateService(db)
    deleted = service.delete_template(template_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Prompt template not found")

    return {"message": "Prompt template deleted successfully"}
