"""Process-specific parameter, target, and feedback field registry."""

PROCESS_REGISTRY = {
    "milling": {
        "parameter_fields": [
            "pulse_width_ps",
            "frequency_kHz",
            "laser_power_W",
            "scan_speed_mm_s",
            "passes",
            "focus_offset_um",
            "fill_pattern",
            "hatch_spacing_um",
            "layer_step_um",
        ],
        "target_fields": ["depth_um", "Sa_um", "Sq_um", "Sz_um", "removal_rate_um3_s"],
        "feedback_fields": ["surface_roughness_level", "depth_level", "efficiency_level"],
    },
    "cutting": {
        "parameter_fields": [
            "pulse_width_ps",
            "frequency_kHz",
            "laser_power_W",
            "scan_speed_mm_s",
            "passes",
            "focus_offset_um",
            "layer_step_um",
            "hatch_spacing_um",
            "fill_pattern",
        ],
        "target_fields": [
            "cut_through",
            "kerf_top_width_um",
            "kerf_bottom_width_um",
            "kerf_taper_deg",
            "cut_edge_Sa_um",
            "HAZ_width_um",
            "chipping_um",
        ],
        "feedback_fields": [
            "cut_through_level",
            "kerf_width_level",
            "edge_roughness_level",
            "taper_level",
            "chipping_level",
            "efficiency_level",
        ],
    },
}
