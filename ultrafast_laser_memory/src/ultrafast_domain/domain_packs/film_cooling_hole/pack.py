from ultrafast_domain.domain_packs.base import DomainPack


PACK = DomainPack(
    name="film_cooling_hole",
    component_types=("film_cooling_hole", "inclined_microhole"),
    quality_metrics=("diameter_error_um", "taper_deg", "recast_layer_um", "fatigue_life", "cooling_efficiency"),
    process_constraints=("incidence_angle_required", "thermal_cycle_and_fatigue_validation_required"),
    trial_templates={"simple_trial_cut": {"representative_geometry": "single_hole_or_small_angle_group"}, "full_trial_cut": {"representative_geometry": "full_hole_pattern"}},
    measurement_templates={"service": {"metrics": ["fatigue_life", "cooling_efficiency", "hole_geometry"]}},
)
