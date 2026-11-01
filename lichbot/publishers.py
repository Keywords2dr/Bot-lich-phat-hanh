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
            # 1. Tìm trong bài ghim (Đáng chú ý) trước
            {"type": "featured", "required_keys": ["lich_phat_hanh_comickd"]},
            # 2. Không có mới tìm qua Album (năm hiện tại -> năm trước)
            {"type": "album", "keys": ["lich phat hanh"]},
            {"type": "album", "keys": ["lich phat hanh"], "year_offset": -1},
            # 3. Cuối cùng mới tìm qua Hashtag
            {"type": "hashtag", "url": KIM_DONG_HASHTAG, "text_key": "kim dong"},
        ),
    ),
    Publisher(
        name="IPM",
        slug="ipmvn",
        sources=(
            # 1. Tìm bài ghim trước
            {
                "type": "featured",
                "required_keys": ["thang_nay_ipm_co_gi"],
                "year_mode": "nearest",
            },
            # 2. Tìm trong album cố định của IPM
            {
                "type": "photos",
                "url": IPM_ALBUM,
                "order": "newest_first",
                "required_keys": ["thang_nay_ipm_co_gi"],
                "year_mode": "nearest",
                "scan_limit": 12,
            },
            # 3. Tìm qua Hashtag
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
            # 1. Tìm bài ghim trước
            {"type": "featured", "required_keys": ["lich phat hanh"]},
            # 2. Tìm trong danh sách Album
            {"type": "album", "keys": ["lich phat hanh"]},
            # 3. Tìm qua Hashtag
            {"type": "hashtag", "url": TRE_HASHTAG, "text_key": "nxb tre"},
        ),
    ),
)