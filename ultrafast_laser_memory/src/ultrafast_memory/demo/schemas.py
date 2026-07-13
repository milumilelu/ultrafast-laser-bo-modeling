from pydantic import BaseModel


class DemoRunRequest(BaseModel):
    approve_review: bool = False
    selected_trial_mode: str | None = None
