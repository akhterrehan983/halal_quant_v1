from app.shariah.schemas import PolicyMode, ScreeningProfile

DEFAULT_PROFILE = ScreeningProfile(
    profile_id="default",
    name="Primary standard",
    standard_ids=["aaoifi_demo_v1"],
    policy=PolicyMode.PRIMARY,
    primary_standard_id="aaoifi_demo_v1",
    review_days=90,
)

_PROFILES: dict[str, ScreeningProfile] = {"default": DEFAULT_PROFILE}


def list_profiles() -> list[ScreeningProfile]:
    return list(_PROFILES.values())


def get_profile(profile_id: str) -> ScreeningProfile | None:
    return _PROFILES.get(profile_id)


def upsert_profile(profile: ScreeningProfile) -> ScreeningProfile:
    _PROFILES[profile.profile_id] = profile
    return profile