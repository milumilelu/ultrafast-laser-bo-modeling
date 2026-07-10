from ultrafast_domain.domain_packs.base import DomainPack
from ultrafast_domain.domain_packs.crl.geometry_rules import validate_crl_geometry
from ultrafast_domain.domain_packs.crl.measurement_templates import MEASUREMENT_TEMPLATES
from ultrafast_domain.domain_packs.crl.process_constraints import PROCESS_CONSTRAINTS
from ultrafast_domain.domain_packs.crl.prompts import PROMPTS
from ultrafast_domain.domain_packs.crl.quality_metrics import QUALITY_METRICS
from ultrafast_domain.domain_packs.crl.trial_templates import TRIAL_TEMPLATES


PACK = DomainPack(
    name="crl",
    component_types=("CRL", "compound_refractive_lens", "xray_lens"),
    quality_metrics=QUALITY_METRICS,
    process_constraints=PROCESS_CONSTRAINTS,
    trial_templates=TRIAL_TEMPLATES,
    measurement_templates=MEASUREMENT_TEMPLATES,
    geometry_validator=validate_crl_geometry,
    prompts=PROMPTS,
)
