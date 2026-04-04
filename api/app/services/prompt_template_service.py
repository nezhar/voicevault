from typing import Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models.prompt_template import PromptTemplate


DEFAULT_PROMPT_TEMPLATES = [
    {
        "label": "Action items",
        "preview_text": "Extract decisions, owners, and deadlines.",
        "body_markdown": "## Action Items\n- List the action items\n- Include owners when available\n- Include due dates when available",
        "sort_order": 10,
        "is_active": True,
    },
    {
        "label": "Key decisions",
        "preview_text": "Summarize the major decisions that were made.",
        "body_markdown": "## Key Decisions\n- Summarize the major decisions\n- Note any context behind each decision",
        "sort_order": 20,
        "is_active": True,
    },
    {
        "label": "Risks and blockers",
        "preview_text": "Highlight open risks, blockers, and follow-up items.",
        "body_markdown": "## Risks and Blockers\n- Identify open risks\n- Identify blockers\n- Note the follow-up needed for each item",
        "sort_order": 30,
        "is_active": True,
    },
]


class PromptTemplateService:
    def __init__(self, db: Session):
        self.db = db

    def list_templates(self, active_only: bool = False) -> list[PromptTemplate]:
        query = self.db.query(PromptTemplate)
        if active_only:
            query = query.filter(PromptTemplate.is_active.is_(True))

        return (
            query.order_by(
                PromptTemplate.sort_order.asc(),
                PromptTemplate.created_at.asc(),
            ).all()
        )

    def get_template(self, template_id: UUID) -> Optional[PromptTemplate]:
        return (
            self.db.query(PromptTemplate)
            .filter(PromptTemplate.id == template_id)
            .first()
        )

    def create_template(
        self,
        *,
        label: str,
        preview_text: Optional[str],
        body_markdown: str,
        sort_order: int = 0,
        is_active: bool = True,
    ) -> PromptTemplate:
        template = PromptTemplate(
            label=label,
            preview_text=preview_text,
            body_markdown=body_markdown,
            sort_order=sort_order,
            is_active=is_active,
        )

        self.db.add(template)
        self.db.commit()
        self.db.refresh(template)
        return template

    def update_template(
        self,
        template_id: UUID,
        *,
        label: Optional[str] = None,
        preview_text: Optional[str] = None,
        body_markdown: Optional[str] = None,
        sort_order: Optional[int] = None,
        is_active: Optional[bool] = None,
    ) -> Optional[PromptTemplate]:
        template = self.get_template(template_id)
        if not template:
            return None

        if label is not None:
            template.label = label
        if preview_text is not None:
            template.preview_text = preview_text
        if body_markdown is not None:
            template.body_markdown = body_markdown
        if sort_order is not None:
            template.sort_order = sort_order
        if is_active is not None:
            template.is_active = is_active

        self.db.commit()
        self.db.refresh(template)
        return template

    def delete_template(self, template_id: UUID) -> bool:
        template = self.get_template(template_id)
        if not template:
            return False

        self.db.delete(template)
        self.db.commit()
        return True

    def seed_defaults_if_empty(self) -> int:
        if self.db.query(PromptTemplate).count() > 0:
            return 0

        templates = [PromptTemplate(**template_data) for template_data in DEFAULT_PROMPT_TEMPLATES]
        self.db.add_all(templates)
        self.db.commit()
        return len(templates)
