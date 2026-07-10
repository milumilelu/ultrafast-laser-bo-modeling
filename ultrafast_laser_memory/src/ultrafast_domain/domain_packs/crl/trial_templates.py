TRIAL_TEMPLATES = {
    "simple_trial_cut": {
        "representative_geometry": "shallow_paraboloid_segment_or_scaled_lens",
        "objectives": ["removal_stability", "form_error", "graphitization", "edge_chipping"],
    },
    "full_trial_cut": {
        "representative_geometry": "full_dual_paraboloid_lens",
        "objectives": ["complete_path", "surface_alignment", "wavefront", "focal_spot", "transmission"],
    },
}
