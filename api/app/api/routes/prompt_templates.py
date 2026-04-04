from typing import List
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.database import get_db
from app.models.schemas import (
    PromptTemplateCreate,
    PromptTemplateResponse,
    PromptTemplateUpdate,
)
from app.services.prompt_template_service import PromptTemplateService

router = APIRouter()


@router.get("/", response_model=List[PromptTemplateResponse])
async def list_prompt_templates(
    active_only: bool = False,
    db: Session = Depends(get_db),
    current_user: bool = Depends(get_current_user),
):
    service = PromptTemplateService(db)
    return service.list_templates(active_only=active_only)


@router.post("/", response_model=PromptTemplateResponse)
async def create_prompt_template(
    template_data: PromptTemplateCreate,
    db: Session = Depends(get_db),
    current_user: bool = Depends(get_current_user),
):
    service = PromptTemplateService(db)
    template = service.create_template(**template_data.dict())
    return template


@router.put("/{template_id}", response_model=PromptTemplateResponse)
async def update_prompt_template(
    template_id: UUID,
    template_data: PromptTemplateUpdate,
    db: Session = Depends(get_db),
    current_user: bool = Depends(get_current_user),
):
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
    current_user: bool = Depends(get_current_user),
):
    service = PromptTemplateService(db)
    deleted = service.delete_template(template_id)

    if not deleted:
        raise HTTPException(status_code=404, detail="Prompt template not found")

    return {"message": "Prompt template deleted successfully"}
