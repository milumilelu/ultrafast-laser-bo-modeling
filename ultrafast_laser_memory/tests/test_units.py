from __future__ import annotations

from ultrafast_memory.normalization.units import normalize_value


def test_unit_normalization():
    assert normalize_value(0.46, "um", "roughness") == (460.0, "nm")
    assert normalize_value(1, "MHz", "frequency") == (1000.0, "kHz")
    assert normalize_value(300, "ps", "pulse_width") == (300000.0, "fs")
    assert normalize_value(60, "mm/min", "scan_speed") == (1.0, "mm/s")
