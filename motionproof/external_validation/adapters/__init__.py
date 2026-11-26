"""Dataset adapters by key."""

from motionproof.external_validation.adapters.anchor_lab import AnchorLab
from motionproof.external_validation.adapters.base import Adapter
from motionproof.external_validation.adapters.compact_sspg import CompactSSPG
from motionproof.external_validation.adapters.kuka_kr300 import KukaKR300
from motionproof.external_validation.adapters.nist_ur5 import NistUR5
from motionproof.external_validation.adapters.stuttgart_te import StuttgartTE

ADAPTERS: dict[str, Adapter] = {a.key: a for a in (AnchorLab(), StuttgartTE(), NistUR5(),
                                                    KukaKR300(), CompactSSPG())}

__all__ = ["ADAPTERS", "Adapter"]
