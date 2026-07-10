from pydantic import BaseModel


class DemoRunRequest(BaseModel):
    approve_review: bool = False
