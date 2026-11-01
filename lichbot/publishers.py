from .models import Publisher

KIM_DONG_HASHTAG = "https://www.facebook.com/hashtag/lich_phat_hanh_comick%C4%91"
IPM_ALBUM = "https://www.facebook.com/media/set/?set=a.452839023556014&type=3"

PUBLISHERS = (
    Publisher(
        name="Kim-Dong",
        slug="nxbkimdong",
        sources=(
            {"type": "album", "keys": ["lich phat hanh"]},
            {"type": "hashtag", "url": KIM_DONG_HASHTAG, "text_key": "kim dong"},
            {"type": "album", "keys": ["lich phat hanh"], "year_offset": -1},
            {"type": "featured", "required_keys": ["lich_phat_hanh_comickd"]},
        ),
    ),
    Publisher(
        name="IPM",
        slug="ipmvn",
        sources=(
            {
                "type": "photos",
                "url": IPM_ALBUM,
                "order": "newest_first",
                "required_keys": ["thang_nay_ipm_co_gi"],
                "year_mode": "nearest",
                "scan_limit": 12,
            },
            {
                "type": "featured",
                "required_keys": ["thang_nay_ipm_co_gi"],
                "year_mode": "nearest",
            },
        ),
    ),
    Publisher(
        name="NXB-Tre",
        slug="truyentranhnxbtre",
        sources=(
            {"type": "featured", "required_keys": ["lich phat hanh"]},
        ),
    ),
)
