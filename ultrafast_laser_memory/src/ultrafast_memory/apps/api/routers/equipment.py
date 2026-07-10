from fastapi import APIRouter, HTTPException

from ultrafast_memory.equipment.schemas import EquipmentProfileCreate, EquipmentProfileUpdate


router = APIRouter(prefix="/equipment", tags=["equipment"])


@router.post("/profiles")
def equipment_profile_create(request: EquipmentProfileCreate) -> dict:
    from ultrafast_memory.db.init_db import init_database
    from ultrafast_memory.equipment.service import create_equipment_profile

    init_database()
    try:
        return create_equipment_profile(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/active")
def equipment_active() -> dict:
    from ultrafast_memory.db.init_db import init_database
    from ultrafast_memory.equipment.service import get_active_equipment_profile

    init_database()
    profile = get_active_equipment_profile()
    return {"active": True, **profile} if profile else {"active": False, "message": "no active equipment profile"}


@router.get("/profiles")
def equipment_profiles() -> list[dict]:
    from ultrafast_memory.db.init_db import init_database
    from ultrafast_memory.equipment.service import list_equipment_profiles

    init_database()
    return list_equipment_profiles()


@router.post("/profiles/{equipment_profile_id}/activate")
def equipment_profile_activate(equipment_profile_id: str) -> dict:
    from ultrafast_memory.db.init_db import init_database
    from ultrafast_memory.equipment.service import activate_equipment_profile

    init_database()
    try:
        return activate_equipment_profile(equipment_profile_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/profiles/{equipment_profile_id}")
def equipment_profile_update(equipment_profile_id: str, request: EquipmentProfileUpdate) -> dict:
    from ultrafast_memory.db.init_db import init_database
    from ultrafast_memory.equipment.service import update_equipment_profile

    init_database()
    try:
        return update_equipment_profile(equipment_profile_id, request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/active/machine-bounds")
def equipment_active_machine_bounds() -> dict:
    from ultrafast_memory.db.init_db import init_database
    from ultrafast_memory.equipment.bounds import build_machine_bounds

    init_database()
    result = build_machine_bounds()
    if not result.get("active"):
        return {"active": False, "machine_bounds": {}, "missing_equipment_fields": result.get("missing_equipment_fields", [])}
    return result


@router.get("/schema")
def equipment_schema() -> dict:
    return {
        "schema_version": 2,
        "required_setup_fields": [
            "wavelength_nm",
            "pulse_width_min_fs",
            "pulse_width_max_fs",
            "rated_max_power_W",
            "actual_max_power_W",
            "frequency_min_kHz",
            "frequency_max_kHz",
            "scan_speed_min_mm_s",
            "scan_speed_max_mm_s",
            "spot_diameter_um",
        ],
        "range_input_format": "min,max",
    }
