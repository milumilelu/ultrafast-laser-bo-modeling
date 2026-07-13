from __future__ import annotations

from abc import ABC, abstractmethod
from copy import deepcopy
import json
from typing import Any


class CamAdapter(ABC):
    @abstractmethod
    def validate_mapping(self, recommendation: dict[str, Any]) -> list[str]: ...

    @abstractmethod
    def map_parameters(self, recommendation: dict[str, Any]) -> dict[str, Any]: ...

    @abstractmethod
    def serialize(self, mapped_parameters: dict[str, Any]) -> str: ...


class GenericJsonCamAdapter(CamAdapter):
    schema_version = "1.0"

    def validate_mapping(self, recommendation: dict[str, Any]) -> list[str]:
        errors = []
        if recommendation.get("status") != "ready_for_cam":
            errors.append("recommendation_not_ready_for_cam")
        if not recommendation.get("complete_recipe"):
            errors.append("complete_recipe_missing")
        metadata = recommendation.get("parameter_metadata") or {}
        for name in recommendation.get("complete_recipe") or {}:
            if name not in metadata:
                errors.append(f"parameter_metadata_missing:{name}")
        return errors

    def map_parameters(self, recommendation: dict[str, Any]) -> dict[str, Any]:
        errors = self.validate_mapping(recommendation)
        if errors:
            raise ValueError(";".join(errors))
        return {
            "schema_version": self.schema_version,
            "recommendation_id": recommendation["recommendation_id"],
            "task_id": recommendation["task_id"],
            "stage": recommendation["stage"],
            "status": recommendation["status"],
            "process_type": recommendation["process_type"],
            "material": recommendation["material"],
            "parameters": deepcopy(recommendation["complete_recipe"]),
            "parameter_metadata": deepcopy(recommendation["parameter_metadata"]),
            "model_version": recommendation.get("model_version"),
            "dataset_version": recommendation.get("dataset_version"),
            "search_space_version": recommendation.get("search_space_version"),
            "created_at": recommendation.get("created_at"),
            "expires_at": recommendation.get("expires_at"),
        }

    def serialize(self, mapped_parameters: dict[str, Any]) -> str:
        return json.dumps(mapped_parameters, ensure_ascii=False, sort_keys=True, indent=2)


class ConfigDrivenCamAdapter(CamAdapter):
    """Validated mapping engine. A profile is not a claim of vendor compatibility."""

    def __init__(self, config: dict[str, Any]):
        self.config = deepcopy(config)
        self.mapping_version = str(config.get("mapping_version") or "unversioned")
        self.format_version = str(config.get("format_version") or "unknown")

    def validate_mapping(self, recommendation: dict[str, Any]) -> list[str]:
        errors = GenericJsonCamAdapter().validate_mapping(recommendation)
        mappings = self.config.get("parameters") or {}
        for internal, spec in mappings.items():
            if spec.get("required") and internal not in recommendation.get("complete_recipe", {}):
                errors.append(f"required_parameter_missing:{internal}")
            if not spec.get("vendor_field"):
                errors.append(f"vendor_field_missing:{internal}")
        return errors

    def map_parameters(self, recommendation: dict[str, Any]) -> dict[str, Any]:
        errors = self.validate_mapping(recommendation)
        if errors:
            raise ValueError(";".join(errors))
        source = deepcopy(recommendation["complete_recipe"])
        mapped: dict[str, Any] = {}
        for internal, spec in (self.config.get("parameters") or {}).items():
            if internal not in source:
                continue
            value = source[internal]
            enum_map = spec.get("enum_map") or {}
            if enum_map:
                if value not in enum_map:
                    raise ValueError(f"unmapped enum value:{internal}:{value}")
                value = enum_map[value]
            conversion = spec.get("unit_conversion")
            if conversion:
                value = float(value) * float(conversion.get("scale", 1.0)) + float(conversion.get("offset", 0.0))
            mapped[spec["vendor_field"]] = value
        return {
            "format_version": self.format_version,
            "mapping_version": self.mapping_version,
            "recommendation_id": recommendation["recommendation_id"],
            "parameters": mapped,
        }

    def serialize(self, mapped_parameters: dict[str, Any]) -> str:
        if self.config.get("serialization", "json") != "json":
            raise ValueError("only JSON serialization is implemented without a verified vendor specification")
        return json.dumps(mapped_parameters, ensure_ascii=False, sort_keys=True, indent=2)

