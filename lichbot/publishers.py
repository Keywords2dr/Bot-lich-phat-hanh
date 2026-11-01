from .models import Publisher

KIM_DONG_HASHTAG = "https://www.facebook.com/hashtag/lich_phat_hanh_comick%C4%91"
IPM_ALBUM = "https://www.facebook.com/media/set/?set=a.452839023556014&type=3"
IPM_HASHTAG = "https://www.facebook.com/hashtag/thang_nay_ipm_co_gi"
TRE_HASHTAG = "https://www.facebook.com/hashtag/lichphathanh"

PUBLISHERS = (
    Publisher(
        name="Kim-Dong",
        slug="nxbkimdong",
        sources=(
            {"type": "featured", "required_keys": ["lich_phat_hanh_comickd"]},
            {"type": "album", "keys": ["lich phat hanh"]},
            {"type": "album", "keys": ["lich phat hanh"], "year_offset": -1},
            {"type": "hashtag", "url": KIM_DONG_HASHTAG, "text_key": "kim dong"},
        ),
    ),
    Publisher(
        name="IPM",
        slug="ipmvn",
        sources=(
            {
                "type": "featured",
                "required_keys": ["thang_nay_ipm_co_gi"],
                "year_mode": "schedule",
            },
            {
                "type": "photos",
                "url": IPM_ALBUM,
                "order": "newest_first",
                "required_keys": ["thang_nay_ipm_co_gi"],
                "year_mode": "schedule",
                "scan_limit": 100,
            },
            {
                "type": "hashtag",
                "url": IPM_HASHTAG,
                "text_key": "ipm",
            },
        ),
    ),
    Publisher(
        name="NXB-Tre",
        slug="truyentranhnxbtre",
        sources=(
            {"type": "featured", "required_keys": ["lich phat hanh"]},
            {"type": "album", "keys": ["lich phat hanh"]},
            {"type": "hashtag", "url": TRE_HASHTAG, "text_key": "nxb tre"},
        ),
    ),
)