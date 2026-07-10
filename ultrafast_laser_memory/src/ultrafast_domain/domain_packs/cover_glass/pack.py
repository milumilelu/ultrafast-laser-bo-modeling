from ultrafast_domain.domain_packs.base import DomainPack


PACK = DomainPack(
    name="cover_glass",
    component_types=("cover_glass", "display_glass"),
    quality_metrics=("edge_chipping_um", "crack_length_um", "surface_roughness_nm", "transmission"),
    process_constraints=("brittle_fracture_control_required", "optical_transmission_must_be_preserved"),
    trial_templates={"simple_trial_cut": {"representative_geometry": "short_line_small_circle_or_single_hole"}, "full_trial_cut": {"representative_geometry": "full_contour_or_pattern"}},
    measurement_templates={"glass": {"metrics": ["edge_chipping_um", "crack_length_um", "transmission"]}},
)
