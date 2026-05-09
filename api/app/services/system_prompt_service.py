from datetime import datetime

from sqlalchemy.orm import Session

from app.models.system_prompt import SystemPrompt

DEFAULT_PROMPTS: dict[str, str] = {
    "chat": (
        'You are an AI assistant helping users analyze and discuss voice transcripts.\n'
        'You have access to a transcript from "{entry_title}".\n\n'
        "TRANSCRIPT:\n"
        "{transcript}\n\n"
        "Guidelines:\n"
        "- Answer questions accurately using only the transcript content\n"
        "- Provide specific quotes when relevant\n"
        "- Help with analysis: key themes, action items, decisions, sentiment\n"
        "- If asked about something not in the transcript, say so clearly\n"
        "- Be concise but thorough"
    ),
    "summary": (
        "You are an expert analyst summarizing voice transcripts.\n"
        "Produce a structured summary with these sections:\n\n"
        "**Key Points** - the 3-5 most important topics discussed\n"
        "**Decisions Made** - concrete decisions or conclusions reached\n"
        "**Action Items** - tasks, owners, and deadlines if mentioned\n"
        "**Open Questions** - unresolved issues or topics needing follow-up\n\n"
        "Be factual. Only include sections where content exists in the transcript."
    ),
}


class SystemPromptService:
    def __init__(self, db: Session):
        self.db = db

    def get_prompt(self, task: str) -> str:
        row = self.db.query(SystemPrompt).filter(SystemPrompt.task == task).first()
        if row:
            return row.body
        return DEFAULT_PROMPTS.get(task, "")

    def update_prompt(self, task: str, body: str) -> SystemPrompt:
        row = self.db.query(SystemPrompt).filter(SystemPrompt.task == task).first()
        if row:
            row.body = body
            row.updated_at = datetime.utcnow()
        else:
            row = SystemPrompt(task=task, body=body, updated_at=datetime.utcnow())
            self.db.add(row)

        self.db.commit()
        self.db.refresh(row)
        return row

    def reset_to_default(self, task: str) -> SystemPrompt:
        return self.update_prompt(task, DEFAULT_PROMPTS[task])

    def seed_defaults(self) -> int:
        inserted = 0

        for task, body in DEFAULT_PROMPTS.items():
            existing = self.db.query(SystemPrompt).filter(SystemPrompt.task == task).first()
            if existing is None:
                self.db.add(SystemPrompt(task=task, body=body, updated_at=datetime.utcnow()))
                inserted += 1

        if inserted:
            self.db.commit()

        return inserted

    def list_prompts(self) -> list[SystemPrompt]:
        return self.db.query(SystemPrompt).all()
