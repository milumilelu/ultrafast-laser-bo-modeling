from __future__ import annotations

from pydantic import BaseModel


class MeasurementSchema(BaseModel):
    measurement_id: str
    metric_name: str
    metric_value: float
    metric_unit: str
