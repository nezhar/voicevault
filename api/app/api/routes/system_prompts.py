from enum import Enum
from typing import List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.database import get_db
from app.models.schemas import SystemPromptResponse, SystemPromptUpdate
from app.services.system_prompt_service import SystemPromptService

router = APIRouter()


class SystemPromptTask(str, Enum):
    chat = "chat"
    summary = "summary"


@router.get("/", response_model=List[SystemPromptResponse])
async def list_system_prompts(
    db: Session = Depends(get_db),
    current_user: bool = Depends(get_current_user),
):
    service = SystemPromptService(db)
    return service.list_prompts()


@router.put("/{task}", response_model=SystemPromptResponse)
async def update_system_prompt(
    task: SystemPromptTask,
    data: SystemPromptUpdate,
    db: Session = Depends(get_db),
    current_user: bool = Depends(get_current_user),
):
    service = SystemPromptService(db)
    return service.update_prompt(task.value, data.body)


@router.post("/{task}/reset", response_model=SystemPromptResponse)
async def reset_system_prompt(
    task: SystemPromptTask,
    db: Session = Depends(get_db),
    current_user: bool = Depends(get_current_user),
):
    service = SystemPromptService(db)
    return service.reset_to_default(task.value)
