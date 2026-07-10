from ultrafast_domain.domain_packs.base import DomainPack


PACK = DomainPack(
    name="surface_texturing",
    component_types=("surface_texture", "microtexture", "bonding_pretreatment"),
    quality_metrics=("texture_depth_um", "pitch_um", "coverage", "surface_roughness", "bond_strength"),
    process_constraints=("representative_area_required", "texture_uniformity_must_be_measured"),
    trial_templates={"simple_trial_cut": {"representative_geometry": "small_groove_dot_or_stripe_patch"}, "full_trial_cut": {"representative_geometry": "full_surface_texture_area"}},
    measurement_templates={"texture": {"metrics": ["texture_depth_um", "pitch_um", "coverage", "bond_strength"]}},
)
