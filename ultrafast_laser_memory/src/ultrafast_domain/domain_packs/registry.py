from __future__ import annotations

from ultrafast_domain.domain_packs.base import DomainPack
from ultrafast_domain.domain_packs.cover_glass.pack import PACK as COVER_GLASS
from ultrafast_domain.domain_packs.crl.pack import PACK as CRL
from ultrafast_domain.domain_packs.film_cooling_hole.pack import PACK as FILM_COOLING_HOLE
from ultrafast_domain.domain_packs.surface_texturing.pack import PACK as SURFACE_TEXTURING
from ultrafast_domain.domain_packs.tgv.pack import PACK as TGV


_PACKS = {
    pack.name: pack
    for pack in (CRL, TGV, FILM_COOLING_HOLE, COVER_GLASS, SURFACE_TEXTURING)
}


def load_domain_pack(name: str) -> DomainPack:
    try:
        return _PACKS[name]
    except KeyError as exc:
        raise KeyError(f"domain pack not found: {name}") from exc


def list_domain_packs() -> list[DomainPack]:
    return [_PACKS[name] for name in sorted(_PACKS)]
