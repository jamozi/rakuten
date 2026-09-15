#!/usr/bin/env python3
"""Generate the ST-1704 theme's optimized raster assets from owner sources."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import stat
import subprocess
import tempfile
from typing import Final, NoReturn


ROOT: Final = Path(__file__).resolve().parents[1]
PORTABLE_POWER_SOURCE: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/"
    "article-portable-power-guide.png"
)
PORTABLE_POWER_OUTPUT: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
    "kurashinoshirube-child/assets/images/article-portable-power-guide.webp"
)
HOME_HERO_SOURCE: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/"
    "home-hero-v2.png"
)
HOME_HERO_OUTPUT: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
    "kurashinoshirube-child/assets/images/home-hero.webp"
)
SUITCASE_GUIDE_SOURCE: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/"
    "article-suitcase-guide-v2.png"
)
SUITCASE_GUIDE_OUTPUT: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
    "kurashinoshirube-child/assets/images/article-suitcase-guide.webp"
)
DISHWASHER_SOURCE: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/"
    "article-countertop-dishwasher-guide.png"
)
DISHWASHER_OUTPUT: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
    "kurashinoshirube-child/assets/images/article-countertop-dishwasher-guide.webp"
)
ROBOT_VACUUM_SOURCE: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/"
    "article-robot-vacuum-guide.png"
)
ROBOT_VACUUM_OUTPUT: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
    "kurashinoshirube-child/assets/images/article-robot-vacuum-guide.webp"
)
SUITCASE_UNDER_100_SOURCE: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/"
    "article-suitcase-under-100-seats.png"
)
SUITCASE_UNDER_100_OUTPUT: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
    "kurashinoshirube-child/assets/images/article-suitcase-under-100-seats.webp"
)
SUITCASE_UNDER_3KG_SOURCE: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/"
    "article-suitcase-under-3kg.png"
)
SUITCASE_UNDER_3KG_OUTPUT: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
    "kurashinoshirube-child/assets/images/article-suitcase-under-3kg.webp"
)
SUITCASE_FRONT_OPEN_SOURCE: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/"
    "article-suitcase-front-open-stopper.png"
)
SUITCASE_FRONT_OPEN_OUTPUT: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
    "kurashinoshirube-child/assets/images/article-suitcase-front-open-stopper.webp"
)
ANKER_GENERATIONS_SOURCE: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/"
    "article-anker-solix-generations.png"
)
ANKER_GENERATIONS_OUTPUT: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
    "kurashinoshirube-child/assets/images/article-anker-solix-generations.webp"
)
SOLOTA_RAKUA_SOURCE: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/"
    "article-solota-rakua-replacement.png"
)
SOLOTA_RAKUA_OUTPUT: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
    "kurashinoshirube-child/assets/images/article-solota-rakua-replacement.webp"
)
ROOMBA_K11_SOURCE: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/"
    "article-roomba-mini-k11-comparison.png"
)
ROOMBA_K11_OUTPUT: Final = (
    ROOT / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/"
    "kurashinoshirube-child/assets/images/article-roomba-mini-k11-comparison.webp"
)
FFMPEG: Final = Path("/usr/bin/ffmpeg")
MAX_SOURCE_BYTES: Final = 8 * 1024 * 1024
MAX_OUTPUT_BYTES: Final = 2 * 1024 * 1024


@dataclass(frozen=True)
class AssetSpec:
    """Closed binding between one reviewed PNG and its deterministic WebP."""

    source: Path
    output: Path
    source_sha256: str
    output_sha256: str
    source_width: int = 1536
    source_height: int = 1024
    output_width: int = 1536
    output_height: int = 1024
    video_filter: str | None = None
    created_on: str = "2026-08-30"
    generation_intent: str = "EDITORIAL_SELECTION_GUIDE"
    allowed_uses: tuple[str, ...] = ("ARTICLE_EDITORIAL_ILLUSTRATION",)


ASSETS: Final = (
    AssetSpec(
        source=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/cleaning-vacuum-20260913.png",
        output=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/cleaning-vacuum-20260913.webp",
        source_sha256="c371a7bae3b27a7ee1ce25e9708dfa012950566783d108f7387e23ee8992e45d",
        output_sha256="8f0e97f57a588482e954f2ffc66f6b91e8bf9fd721be32ba09b347d04519abcf",
        source_width=1536,
        source_height=1024,
        output_width=900,
        output_height=600,
        video_filter="scale=900:600:flags=lanczos",
        created_on="2026-09-13",
        generation_intent="ANONYMOUS_CATEGORY_CLEANING",
        allowed_uses=("CATEGORY_EDITORIAL_ILLUSTRATION",),
    ),
    AssetSpec(
        source=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/cleaning-mop-20260913.png",
        output=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/cleaning-mop-20260913.webp",
        source_sha256="a09a17eb85e64c475129ede959518dcb9de16381d60e566d14dccdaa4d2b5941",
        output_sha256="f6478cefb6d8dc7578bbfa00e644ef37e5868bf5f506d4e068b56f85ec05b9a4",
        source_width=1536,
        source_height=1024,
        output_width=900,
        output_height=600,
        video_filter="scale=900:600:flags=lanczos",
        created_on="2026-09-13",
        generation_intent="ANONYMOUS_CATEGORY_CLEANING",
        allowed_uses=("CATEGORY_EDITORIAL_ILLUSTRATION",),
    ),
    AssetSpec(
        source=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/cleaning-manual-20260913.png",
        output=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/cleaning-manual-20260913.webp",
        source_sha256="fba7dc299566d9bc0345650f65a8a3ebe5e4b688c9ba22f0774f1b120d431438",
        output_sha256="58419320671c7ee81c3242afaeab6b3b3d56f53d34022ee5c5c85ed52cde34f1",
        source_width=1536,
        source_height=1024,
        output_width=900,
        output_height=600,
        video_filter="scale=900:600:flags=lanczos",
        created_on="2026-09-13",
        generation_intent="ANONYMOUS_CATEGORY_CLEANING",
        allowed_uses=("CATEGORY_EDITORIAL_ILLUSTRATION",),
    ),
    AssetSpec(
        source=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/cleaning-dust-20260913.png",
        output=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/cleaning-dust-20260913.webp",
        source_sha256="516a7422623790972488fb026c57401517ebc4e6d40c86918280246dc5be5e73",
        output_sha256="55e9e83b55eca1e692e7d0dd066ed5e541ce528f42e9ce1d3c81f40e177b4559",
        source_width=1536,
        source_height=1024,
        output_width=900,
        output_height=600,
        video_filter="scale=900:600:flags=lanczos",
        created_on="2026-09-13",
        generation_intent="ANONYMOUS_CATEGORY_CLEANING",
        allowed_uses=("CATEGORY_EDITORIAL_ILLUSTRATION",),
    ),
    AssetSpec(
        source=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/cleaning-wash-20260913.png",
        output=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/cleaning-wash-20260913.webp",
        source_sha256="86440371bb8826370884b9027b7c1d33248879210a1a0f7a838a89af49ea5aa0",
        output_sha256="94a95c0c3697ed8e985a73721cd8126e1d97cdfd4281824f7fa1bc0f3dd70f1c",
        source_width=1536,
        source_height=1024,
        output_width=900,
        output_height=600,
        video_filter="scale=900:600:flags=lanczos",
        created_on="2026-09-13",
        generation_intent="ANONYMOUS_CATEGORY_CLEANING",
        allowed_uses=("CATEGORY_EDITORIAL_ILLUSTRATION",),
    ),
    AssetSpec(
        source=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/travel-small-20260913.png",
        output=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/travel-small-20260913.webp",
        source_sha256="777915758f42a2471fc9b95f58b45399451bc55ec94ef38693b50c18fd96304b",
        output_sha256="db5b597e3d7b58683f1ca7172e35d45a3e500d7f6e5b969d7b97199d1038cbed",
        source_width=1448,
        source_height=1086,
        output_width=900,
        output_height=675,
        video_filter="scale=900:675:flags=lanczos",
        created_on="2026-09-13",
        generation_intent="ANONYMOUS_CATEGORY_TRAVEL",
        allowed_uses=(
            "CATEGORY_EDITORIAL_ILLUSTRATION",
            "HOMEPAGE_RECENT_ARTICLE_THUMBNAIL",
            "SOCIAL_PREVIEW",
        ),
    ),
    AssetSpec(
        source=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/travel-medium-20260913.png",
        output=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/travel-medium-20260913.webp",
        source_sha256="16013a3b0f83c2224afe5243995c63a4d1e6811bfb3904cd2ddd09844ac1842d",
        output_sha256="153359cc150bd780c7cd4cbac128047b429b97420cb29cb5e07bc5a6239f7161",
        source_width=1448,
        source_height=1086,
        output_width=900,
        output_height=675,
        video_filter="scale=900:675:flags=lanczos",
        created_on="2026-09-13",
        generation_intent="ANONYMOUS_CATEGORY_TRAVEL",
        allowed_uses=("CATEGORY_EDITORIAL_ILLUSTRATION",),
    ),
    AssetSpec(
        source=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/travel-large-20260913.png",
        output=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/travel-large-20260913.webp",
        source_sha256="99966c44b8a17ab13f3de7038ff4effe33cc17761d6e4d38b68823b0606d37c4",
        output_sha256="b04dfaba611c040064441e2c0d8206486d8c85fe7ad3fad74783766aba028983",
        source_width=1448,
        source_height=1086,
        output_width=900,
        output_height=675,
        video_filter="scale=900:675:flags=lanczos",
        created_on="2026-09-13",
        generation_intent="ANONYMOUS_CATEGORY_TRAVEL",
        allowed_uses=("CATEGORY_EDITORIAL_ILLUSTRATION",),
    ),
    AssetSpec(
        source=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/travel-light-20260913.png",
        output=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/travel-light-20260913.webp",
        source_sha256="a8abda6b7a0d5d309088063eab30ef955fe515c01441369db73188130107a88c",
        output_sha256="798f9e48dfaa30e2bb890750f5d3463ce54deeca5f0b3fbc98f33150e8c9d814",
        source_width=1448,
        source_height=1086,
        output_width=900,
        output_height=675,
        video_filter="scale=900:675:flags=lanczos",
        created_on="2026-09-13",
        generation_intent="ANONYMOUS_CATEGORY_TRAVEL",
        allowed_uses=("CATEGORY_EDITORIAL_ILLUSTRATION",),
    ),
    AssetSpec(
        source=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/travel-access-20260913.png",
        output=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/travel-access-20260913.webp",
        source_sha256="d3ced595c8656fb43b446174173077370bef950d33a7dede08b0e7893531152b",
        output_sha256="de0bdb2aaea722ca58640df54a3815c89263bdf1020ff6c1910fb4a7772d30fd",
        source_width=1448,
        source_height=1086,
        output_width=900,
        output_height=675,
        video_filter="scale=900:675:flags=lanczos",
        created_on="2026-09-13",
        generation_intent="ANONYMOUS_CATEGORY_TRAVEL",
        allowed_uses=("CATEGORY_EDITORIAL_ILLUSTRATION",),
    ),
    AssetSpec(
        source=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/travel-move-20260913.png",
        output=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/travel-move-20260913.webp",
        source_sha256="09efe511375cc9490eca06244b1cca90c8e0b0f8d6e3512757f37ecfed7023e7",
        output_sha256="da8d443ec76385aec82ecab4554c0357b67f27a13f7bd54f90ec236d0817df8f",
        source_width=1448,
        source_height=1086,
        output_width=900,
        output_height=675,
        video_filter="scale=900:675:flags=lanczos",
        created_on="2026-09-13",
        generation_intent="ANONYMOUS_CATEGORY_TRAVEL",
        allowed_uses=("CATEGORY_EDITORIAL_ILLUSTRATION",),
    ),
    AssetSpec(
        source=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/power-capacity-small-20260913.png",
        output=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/power-capacity-small-20260913.webp",
        source_sha256="f1ced6fc365023a1c7dbb2077249189b033f9dd6e13c274b4dd27b245e1e2458",
        output_sha256="f7602b7505592df2d42f765bbdf1c2d3d0d7a9436ba5cb04feaec18be6de24ce",
        source_width=1536,
        source_height=1024,
        output_width=900,
        output_height=600,
        video_filter="scale=900:600:flags=lanczos",
        created_on="2026-09-13",
        generation_intent="ANONYMOUS_CATEGORY_PREPAREDNESS",
        allowed_uses=("CATEGORY_EDITORIAL_ILLUSTRATION",),
    ),
    AssetSpec(
        source=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/power-capacity-medium-20260913.png",
        output=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/power-capacity-medium-20260913.webp",
        source_sha256="9dee1908f21d836e4f070416a16be9025edcbb56d52e93252fd8f3cc02655202",
        output_sha256="6ac70394c787d699df91a6e4d18978864ccda763a9c3ba0598a37e349fd7bcf5",
        source_width=1536,
        source_height=1024,
        output_width=900,
        output_height=600,
        video_filter="scale=900:600:flags=lanczos",
        created_on="2026-09-13",
        generation_intent="ANONYMOUS_CATEGORY_PREPAREDNESS",
        allowed_uses=("CATEGORY_EDITORIAL_ILLUSTRATION",),
    ),
    AssetSpec(
        source=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/power-capacity-large-20260913.png",
        output=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/power-capacity-large-20260913.webp",
        source_sha256="d9388ee5fb15800c30b88aa1a838192569ab42376d5ef9a6af8d4e6072b86c2f",
        output_sha256="3e0431641a002ece5c09e032446e61b5e227daa9d88e6ca4237e2e6a051c7b69",
        source_width=1536,
        source_height=1024,
        output_width=900,
        output_height=600,
        video_filter="scale=900:600:flags=lanczos",
        created_on="2026-09-13",
        generation_intent="ANONYMOUS_CATEGORY_PREPAREDNESS",
        allowed_uses=("CATEGORY_EDITORIAL_ILLUSTRATION",),
    ),
    AssetSpec(
        source=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/kitchen-capacity-compact-20260913.png",
        output=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/kitchen-capacity-compact-20260913.webp",
        source_sha256="5644f9c3e8a018ea155896e9458f996f54a0fa86e17b4bb20a813d372bf11ff5",
        output_sha256="f46216dccb204f7791fd30ef30f6be619d63810088c13c8d892aaecbdcdddabe",
        output_width=900,
        output_height=600,
        video_filter="scale=900:600:flags=lanczos",
        created_on="2026-09-13",
        generation_intent="CONCEPTUAL_DISH_AMOUNT_COMPACT",
        allowed_uses=(
            "CATEGORY_CAPACITY_EDITORIAL_ILLUSTRATION",
            "ARTICLE_EDITORIAL_ILLUSTRATION",
            "HOMEPAGE_RECENT_ARTICLE_THUMBNAIL",
        ),
    ),
    AssetSpec(
        source=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/kitchen-capacity-standard-20260913.png",
        output=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/kitchen-capacity-standard-20260913.webp",
        source_sha256="12a8b050904326f7e70a3536ae7c21b126b9560c8990db84b322251f2b9a7e28",
        output_sha256="6c1c766e69b7e39634f0363e087f255ed21ede528ce3d505a3c0eb5b03027a37",
        output_width=900,
        output_height=600,
        video_filter="scale=900:600:flags=lanczos",
        created_on="2026-09-13",
        generation_intent="CONCEPTUAL_DISH_AMOUNT_STANDARD",
        allowed_uses=(
            "CATEGORY_CAPACITY_EDITORIAL_ILLUSTRATION",
            "ARTICLE_EDITORIAL_ILLUSTRATION",
            "HOMEPAGE_RECENT_ARTICLE_THUMBNAIL",
        ),
    ),
    AssetSpec(
        source=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/kitchen-capacity-large-20260913.png",
        output=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/kitchen-capacity-large-20260913.webp",
        source_sha256="4e2282644d880712f2b8f493c5fc2cd668ee1e1caf20b8978ca0ac3f8404d0cf",
        output_sha256="aa69f7b790fe7e595789d7ed79e23089bea15b3aadde17089bffae684c92a3a8",
        output_width=900,
        output_height=600,
        video_filter="scale=900:600:flags=lanczos",
        created_on="2026-09-13",
        generation_intent="CONCEPTUAL_DISH_AMOUNT_LARGE",
        allowed_uses=(
            "CATEGORY_CAPACITY_EDITORIAL_ILLUSTRATION",
            "ARTICLE_EDITORIAL_ILLUSTRATION",
            "HOMEPAGE_RECENT_ARTICLE_THUMBNAIL",
        ),
    ),
    AssetSpec(
        source=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/home-recent-cost-20260913.png",
        output=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/home-recent-cost-20260913.webp",
        source_sha256="2ca25edb8d70962bddfd27eb82ef152a44bdf580de329a01d90a03149a06a714",
        output_sha256="ca474cabf712dab358947cdb2682c2acf41b514c0d9a9a999899f16adff4a1a7",
        output_width=900,
        output_height=600,
        video_filter="scale=900:600:flags=lanczos",
        created_on="2026-09-13",
        generation_intent="ANONYMOUS_DISHWASHER_COST_STILL_LIFE",
        allowed_uses=("HOMEPAGE_RECENT_ARTICLE_THUMBNAIL",),
    ),
    AssetSpec(
        source=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/home-recent-cleaning-20260913.png",
        output=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/home-recent-cleaning-20260913.webp",
        source_sha256="985571c9781f21c5deac335b082883c75896f058c7c14f002c7930aad9fb4e79",
        output_sha256="4c8c76f65516d70838ce5db860606f351ab56fc6e7f0f9515748eeb5fae1c678",
        output_width=900,
        output_height=600,
        video_filter="scale=900:600:flags=lanczos",
        created_on="2026-09-13",
        generation_intent="ANONYMOUS_DISHWASHER_CLEANING_STILL_LIFE",
        allowed_uses=("HOMEPAGE_RECENT_ARTICLE_THUMBNAIL", "CATEGORY_GUIDE_THUMBNAIL"),
    ),
    AssetSpec(
        source=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/home-recent-detergent-20260913.png",
        output=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/home-recent-detergent-20260913.webp",
        source_sha256="9daa39068a9e65eb4f952f900ed4aea2e93b20f8ce66d1e759b2302c4f95cb7e",
        output_sha256="9f8162b99854100fe09846e91aab4ef80978afdb80efdd96c41e9c3e339c53f1",
        output_width=900,
        output_height=600,
        video_filter="scale=900:600:flags=lanczos",
        created_on="2026-09-13",
        generation_intent="ANONYMOUS_DISHWASHER_DETERGENT_STILL_LIFE",
        allowed_uses=("HOMEPAGE_RECENT_ARTICLE_THUMBNAIL", "CATEGORY_GUIDE_THUMBNAIL"),
    ),
    AssetSpec(
        source=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/home-recent-water-20260913.png",
        output=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/home-recent-water-20260913.webp",
        source_sha256="8828c8cb7b26cd30c86e8d07ccf45f6d3687650e2d8e5d5d33e3cac372c2027d",
        output_sha256="7decdb2892a5ea9ac2e488c015060fde18893f578bcf69b56639bed52814c916",
        output_width=900,
        output_height=600,
        video_filter="scale=900:600:flags=lanczos",
        created_on="2026-09-13",
        generation_intent="ANONYMOUS_DISHWASHER_WATER_STILL_LIFE",
        allowed_uses=("HOMEPAGE_RECENT_ARTICLE_THUMBNAIL", "CATEGORY_GUIDE_THUMBNAIL"),
    ),
    AssetSpec(
        source=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/media/source-images/home-lifestyle-20260913.png",
        output=ROOT
        / "changes/st-1704/self-hosted-editorial-pilot-v1/theme/kurashinoshirube-child/assets/images/home-lifestyle-20260913.webp",
        source_sha256="8b272be7c7e1a9be6b113d68f4afd1d3874bbced08e4d839b2d032ff680ec38e",
        output_sha256="8e8a39c5d34f41a889968de911fb8659b36ebc4e9c95bd2541797affa59943fe",
        source_width=1672,
        source_height=941,
        output_width=1672,
        output_height=941,
        created_on="2026-09-13",
        generation_intent="ANONYMOUS_QUIET_LIVING_EDITORIAL",
        allowed_uses=("HOMEPAGE_HERO",),
    ),
    AssetSpec(
        source=HOME_HERO_SOURCE,
        output=HOME_HERO_OUTPUT,
        source_sha256=(
            "91dc5bdd9d0047b45a324ca0aa72c3fe8bf5060baf9f8c52d59e022c81f24252"
        ),
        output_sha256=(
            "9a2d6d390ffd4ef0642d4c0a7a12da9daf7e904934ffd3f9e95e29907aedc493"
        ),
        source_width=1672,
        source_height=941,
        output_width=1600,
        output_height=900,
        video_filter="crop=1672:940:0:0,scale=1600:900:flags=lanczos",
        created_on="2026-08-31",
        generation_intent="ABSTRACT_EDITORIAL_PURCHASE_DECISION",
        allowed_uses=("HOMEPAGE_HERO", "SOCIAL_PREVIEW_FALLBACK"),
    ),
    AssetSpec(
        source=SUITCASE_GUIDE_SOURCE,
        output=SUITCASE_GUIDE_OUTPUT,
        source_sha256=(
            "14377a0035501c42e467e2fe962bef91059723992ddf35975a4106fb7ce7c949"
        ),
        output_sha256=(
            "dc8133377f21355ac0c187273d70904c305dd5687bf0e5e8ce3af76fab668046"
        ),
        source_width=1672,
        source_height=941,
        output_width=1600,
        output_height=900,
        video_filter="crop=1672:940:0:0,scale=1600:900:flags=lanczos",
        created_on="2026-08-31",
        generation_intent="GENERIC_SUITCASE_DIMENSION_AND_CAPACITY_COMPARISON",
        allowed_uses=("SUITCASE_ARTICLE_HEADER",),
    ),
    AssetSpec(
        source=PORTABLE_POWER_SOURCE,
        output=PORTABLE_POWER_OUTPUT,
        source_sha256=(
            "703444cdf29740bb72de42d09c7c7222a3ee46a09bcaf4f78875df9131cc56d6"
        ),
        output_sha256=(
            "54b84689cff952f6a384982b89d2f56adfbdeff9ff03fe628fcaf5a949ab0f5a"
        ),
        created_on="2026-08-28",
        generation_intent="PORTABLE_POWER_SELECTION_GUIDE",
        allowed_uses=("PORTABLE_POWER_ARTICLE_HEADER",),
    ),
    AssetSpec(
        source=DISHWASHER_SOURCE,
        output=DISHWASHER_OUTPUT,
        source_sha256=(
            "26e50a383b313d79e65999e100fc82037a434550136fb293c3f20574965d090a"
        ),
        output_sha256=(
            "c36e87682ce9be33f70bc5b1a55e20a63b19ab6155172d670d5c019a984bcf9f"
        ),
        generation_intent="COUNTERTOP_DISHWASHER_SELECTION_GUIDE",
        allowed_uses=("DISHWASHER_ARTICLE_ILLUSTRATION",),
    ),
    AssetSpec(
        source=ROBOT_VACUUM_SOURCE,
        output=ROBOT_VACUUM_OUTPUT,
        source_sha256=(
            "2ecd4dc8e55ea70a76287df30e44c874fea6292bf1be457934e049f1cfbcee4b"
        ),
        output_sha256=(
            "f589471aeed1064f2499ec5d32a8e9c4b6b14db8613d3b1743b37d245ecc2384"
        ),
        generation_intent="ROBOT_VACUUM_SELECTION_GUIDE",
        allowed_uses=("ROBOT_VACUUM_ARTICLE_ILLUSTRATION",),
    ),
    AssetSpec(
        source=SUITCASE_UNDER_100_SOURCE,
        output=SUITCASE_UNDER_100_OUTPUT,
        source_sha256=(
            "9869fd732cd56a1153159b6147da25a6cb569969a3683685d1d14310ee010cdc"
        ),
        output_sha256=(
            "0a2682459af1562593ccae37a877bbae26585f269c86d79775e98c015fd40f10"
        ),
        created_on="2026-09-01",
        generation_intent="UNDER_100_SEAT_CARRY_ON_DIMENSION_COMPARISON",
        allowed_uses=("UNDER_100_SEAT_SUITCASE_ARTICLE_HEADER",),
    ),
    AssetSpec(
        source=SUITCASE_UNDER_3KG_SOURCE,
        output=SUITCASE_UNDER_3KG_OUTPUT,
        source_sha256=(
            "2a8521d52a85e0ad320dbed37fe279ff89b8f1c632839eeba2f27efd494ed089"
        ),
        output_sha256=(
            "43db66a0e12a20cc8f31f44293691811734a41b0d0afa0374c73cf95d6cfd394"
        ),
        created_on="2026-09-01",
        generation_intent="UNDER_3KG_CARRY_ON_WEIGHT_AND_CAPACITY_COMPARISON",
        allowed_uses=("UNDER_3KG_SUITCASE_ARTICLE_HEADER",),
    ),
    AssetSpec(
        source=SUITCASE_FRONT_OPEN_SOURCE,
        output=SUITCASE_FRONT_OPEN_OUTPUT,
        source_sha256=(
            "8005abfdce55db8f9e31c03f907040e07bd7afe103333387a2796e27b105975b"
        ),
        output_sha256=(
            "6cffe92e50ce644ae60c72d4acaece34609acaa25a943a41811833063afb9d1e"
        ),
        source_width=1535,
        output_width=1536,
        video_filter="scale=1536:1024:flags=lanczos",
        created_on="2026-09-01",
        generation_intent="FRONT_OPEN_STOPPER_CARRY_ON_FEATURE_COMPARISON",
        allowed_uses=("FRONT_OPEN_STOPPER_SUITCASE_ARTICLE_HEADER",),
    ),
    AssetSpec(
        source=ANKER_GENERATIONS_SOURCE,
        output=ANKER_GENERATIONS_OUTPUT,
        source_sha256=(
            "2eec59720c0bce9d6537beeb5f5497b368f18d713dd0020eee91e65e74c6281c"
        ),
        output_sha256=(
            "b8db0de1e65653539d327c3645f8c0722a71be1b2a8291c338ce7b37bd5545a0"
        ),
        created_on="2026-09-01",
        generation_intent="ANKER_SOLIX_GENERATION_AND_OUTPUT_COMPARISON",
        allowed_uses=("ANKER_SOLIX_COMPARISON_ARTICLE_HEADER",),
    ),
    AssetSpec(
        source=SOLOTA_RAKUA_SOURCE,
        output=SOLOTA_RAKUA_OUTPUT,
        source_sha256=(
            "254ff9a0d263282ffd58b976dfb9122ac18bad3c482031e496655750f045c5a2"
        ),
        output_sha256=(
            "a413f3c1a70282eb0d1362959f746421bec4c1fc640f072eb045d9c4009d3374"
        ),
        created_on="2026-09-01",
        generation_intent="SOLOTA_RAKUA_REPLACEMENT_CONDITION_COMPARISON",
        allowed_uses=("SOLOTA_RAKUA_COMPARISON_ARTICLE_HEADER",),
    ),
    AssetSpec(
        source=ROOMBA_K11_SOURCE,
        output=ROOMBA_K11_OUTPUT,
        source_sha256=(
            "5500d9395c9444e16f4a854d6f4e3c5b4e237342995afd501bab3e78bf829023"
        ),
        output_sha256=(
            "a601dd1913fe0c54551e9e894666dd5dd793b36e193d47bb292e85ed22a2b1d2"
        ),
        created_on="2026-09-01",
        generation_intent="ROOMBA_MINI_SWITCHBOT_K11_SIZE_AND_STATION_COMPARISON",
        allowed_uses=("ROOMBA_K11_COMPARISON_ARTICLE_HEADER",),
    ),
)

# Compatibility aliases for callers that identify the original portable-power asset.
SOURCE: Final = PORTABLE_POWER_SOURCE
OUTPUT: Final = PORTABLE_POWER_OUTPUT
SOURCE_SHA256: Final = next(
    asset.source_sha256 for asset in ASSETS if asset.source == PORTABLE_POWER_SOURCE
)
OUTPUT_SHA256: Final = next(
    asset.output_sha256 for asset in ASSETS if asset.output == PORTABLE_POWER_OUTPUT
)


class AssetGenerationFailure(RuntimeError):
    """Stable, non-sensitive asset generation refusal."""


def _fail() -> NoReturn:
    raise AssetGenerationFailure("ST1704_THEME_ASSET_GENERATION_INVALID") from None


def _regular_payload(path: Path, maximum: int) -> bytes:
    try:
        metadata = path.lstat()
        payload = path.read_bytes()
    except OSError:
        _fail()
    if (
        path.is_symlink()
        or not stat.S_ISREG(metadata.st_mode)
        or metadata.st_size <= 0
        or metadata.st_size > maximum
        or len(payload) != metadata.st_size
    ):
        _fail()
    return payload


def _validate_source(asset: AssetSpec) -> None:
    payload = _regular_payload(asset.source, MAX_SOURCE_BYTES)
    if (
        hashlib.sha256(payload).hexdigest() != asset.source_sha256
        or len(payload) < 33
        or payload[:8] != b"\x89PNG\r\n\x1a\n"
        or payload[12:16] != b"IHDR"
        or int.from_bytes(payload[16:20], "big") != asset.source_width
        or int.from_bytes(payload[20:24], "big") != asset.source_height
        or b"c2pa" not in payload
        or b"OpenAI Media Service API" not in payload
    ):
        _fail()


def manifest_provenance(asset: AssetSpec) -> dict[str, object]:
    """Return the closed, non-prompt provenance record for a generated asset."""

    return {
        "allowed_modifications": [
            "CROP",
            "FORMAT_CONVERSION",
            "RESIZE",
            "WEB_OPTIMIZATION",
        ],
        "allowed_uses": list(asset.allowed_uses),
        "created_on": asset.created_on,
        "creation_method": "OPENAI_IMAGE_GENERATION",
        "creator_record": "SITE_OWNER_DIRECTED_OPENAI_MEDIA_SERVICE",
        "external_license_dependency": False,
        "generation_intent": asset.generation_intent,
        "original_sha256": asset.source_sha256,
        "original_source_path": asset.source.relative_to(ROOT).as_posix(),
        "provenance_evidence": "C2PA_OPENAI_MEDIA_SERVICE_API",
        "rights_basis": "OWNER_AUTHORIZED_GENERATION_FOR_THIS_SITE",
        "rights_status": "RECORDED_FOR_SITE_USE",
    }


def _validate_webp(payload: bytes, asset: AssetSpec) -> None:
    if (
        len(payload) < 20
        or len(payload) > MAX_OUTPUT_BYTES
        or payload[:4] != b"RIFF"
        or payload[8:12] != b"WEBP"
        or int.from_bytes(payload[4:8], "little") != len(payload) - 8
        or b"ANIM" in payload[:128]
        or b"ANMF" in payload
    ):
        _fail()
    dimensions = _webp_dimensions(payload)
    if dimensions != (asset.output_width, asset.output_height):
        _fail()


def _webp_dimensions(payload: bytes) -> tuple[int, int] | None:
    vp8 = payload.find(b"VP8 ")
    if vp8 < 0 or vp8 + 30 > len(payload):
        return None
    frame = vp8 + 8
    if payload[frame + 3 : frame + 6] != b"\x9d\x01\x2a":
        return None
    width = int.from_bytes(payload[frame + 6 : frame + 8], "little") & 0x3FFF
    height = int.from_bytes(payload[frame + 8 : frame + 10], "little") & 0x3FFF
    return (width, height)


def _render(asset: AssetSpec, directory: Path) -> bytes:
    target = directory / asset.output.name
    environment = {
        "HOME": "/nonexistent",
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": "/usr/bin:/bin",
        "TZ": "UTC",
    }
    command = [
        FFMPEG.as_posix(),
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        asset.source.as_posix(),
        "-map_metadata",
        "-1",
        "-frames:v",
        "1",
        "-an",
        "-sn",
        "-dn",
    ]
    if asset.video_filter is not None:
        command.extend(["-vf", asset.video_filter])
    command.extend(
        [
            "-c:v",
            "libwebp",
            "-lossless",
            "0",
            "-quality",
            "82",
            "-compression_level",
            "6",
            "-preset",
            "picture",
            "-pix_fmt",
            "yuv420p",
            "-threads",
            "1",
            "-f",
            "webp",
            "-y",
            target.as_posix(),
        ]
    )
    try:
        version = subprocess.run(
            [FFMPEG.as_posix(), "-version"],
            check=True,
            capture_output=True,
            env=environment,
            timeout=10,
        )
        if not version.stdout.startswith(b"ffmpeg version 4.4.2"):
            _fail()
        subprocess.run(
            command,
            check=True,
            capture_output=True,
            env=environment,
            timeout=120,
        )
    except OSError, subprocess.SubprocessError:
        _fail()
    payload = _regular_payload(target, MAX_OUTPUT_BYTES)
    _validate_webp(payload, asset)
    return payload


def generate(*, check: bool) -> dict[str, str]:
    digests: dict[str, str] = {}
    for asset in ASSETS:
        _validate_source(asset)
        if check:
            payload = _regular_payload(asset.output, MAX_OUTPUT_BYTES)
            _validate_webp(payload, asset)
        else:
            with tempfile.TemporaryDirectory(prefix="raos-st1704-theme-asset.") as raw:
                payload = _render(asset, Path(raw))
        digest = hashlib.sha256(payload).hexdigest()
        if digest != asset.output_sha256:
            _fail()
        if not check:
            try:
                asset.output.parent.mkdir(parents=True, exist_ok=True)
                temporary = asset.output.with_name(
                    f".{asset.output.name}.{os.getpid()}.tmp"
                )
                descriptor = os.open(
                    temporary,
                    os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW,
                    0o644,
                )
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(temporary, asset.output)
            except OSError:
                _fail()
        digests[asset.output.name] = digest
    return digests


def main() -> int:
    parser = argparse.ArgumentParser(allow_abbrev=False)
    parser.add_argument("--check", action="store_true")
    arguments = parser.parse_args()
    try:
        digests = generate(check=arguments.check)
    except AssetGenerationFailure as error:
        print(str(error), file=os.sys.stderr)
        return 1
    inventory = ",".join(f"{name}:{digest}" for name, digest in digests.items())
    print(f"ST1704_THEME_ASSETS_OK assets={len(digests)} sha256={inventory}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
