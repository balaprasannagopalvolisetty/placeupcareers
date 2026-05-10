from pydantic import BaseModel, Field


class AlertSetting(BaseModel):
    email_alerts: bool = True
    daily_digest: bool = True
    weekly_report: bool = False


class AlertItem(BaseModel):
    id: str
    title: str
    company: str
    location: str
    salary: str
    match: int = Field(default=0)
    visa: str = ""
    time: str
    unread: bool = True


class AlertCreateRequest(BaseModel):
    title: str
    company: str = ""
    location: str = ""
    salary: str = ""
    visa: str = ""
    match: int = 0
    message: str | None = None
