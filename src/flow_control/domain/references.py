from dataclasses import dataclass, field


@dataclass(frozen=True)
class TagReference:
    attribute_tag: str
    eta_typical: float | None = None
    baseline_stagnation: float | None = None
    sample_count: int = 0  # 集約元テナント数


@dataclass(frozen=True)
class Reference:
    by_attribute_tag: tuple[TagReference, ...] = field(default_factory=tuple)
    source_k_anonymity: int = 0  # 参考情報，K>=5 の場合のみ信頼

    def tag_reference_of(self, attribute_tag: str) -> TagReference | None:
        for tag_reference in self.by_attribute_tag:
            if tag_reference.attribute_tag == attribute_tag:
                return tag_reference
        return None
