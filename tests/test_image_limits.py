import pytest

from app.core.errors import NuvlyError
from app.modules.domain.image_limits import (
    project_video_quota,
    validate_project_media_quota,
    validate_website_image_quota,
    website_image_quota,
)


def project(count, tier="plus", product="website"):
    return {
        "productType": product,
        "planTier": tier,
        "blocks": [{"id": "a", "props": {f"image{i}": f"/static/uploads/customer/{i}.png" for i in range(count)}}],
    }


@pytest.mark.parametrize(
    "product,tier,limit",
    [
        ("website", "plus", 16),
        ("website", "pro", 24),
        ("invitation", "plus", 8),
        ("invitation", "pro", 16),
        ("website", "custom", 60),
    ],
)
def test_plan_limits_and_server_rejection(product, tier, limit):
    assert validate_website_image_quota(project(limit, tier, product))["used"] == limit
    with pytest.raises(NuvlyError) as error:
        validate_website_image_quota(project(limit + 1, tier, product))
    assert error.value.code == "IMAGE_QUOTA_EXCEEDED"


def test_template_stock_images_count_and_reused_images_only_count_once():
    template = project(12)
    p = project(12)
    p["blocks"][0]["props"].update(
        {
            "ownImage": "/static/uploads/own.png",
            "duplicateImage": "https://api.test/static/uploads/own.png",
            "stockImage": "/assets/stock.png",
        }
    )
    quota = validate_website_image_quota(p, template)
    assert quota["used"] == 14
    assert quota["includesTemplateImages"] is True


def test_canonical_and_linked_pages_include_hidden_sections_and_gallery_src():
    p = project(1)
    p["pages"] = [
        {"blocks": [{"id": "linked", "enabled": False, "props": {"images": [{"src": "/assets/linked.png"}]}}]}
    ]
    p["metadata"] = {"linkedPages": [{"blocks": [{"props": {"itemsText": "Foto|/assets/item.jpg"}}]}]}
    assert website_image_quota(p)["used"] == 2


def test_props_override_legacy_settings():
    p = {"blocks": [{"props": {"coverImage": "/assets/new.png"}, "settings": {"coverImage": "/assets/old.png"}}]}
    assert website_image_quota(p)["used"] == 1


@pytest.mark.parametrize("product", ["website", "invitation"])
def test_basic_has_no_video_and_advanced_has_one_including_template_videos(product):
    p = project(1, "plus", product)
    p["blocks"][0]["props"]["videoUrl"] = "https://youtu.be/abcdefghijk"
    with pytest.raises(NuvlyError) as error:
        validate_project_media_quota(p)
    assert error.value.code == "VIDEO_QUOTA_EXCEEDED"
    p["planTier"] = "pro"
    validate_project_media_quota(p)
    p["blocks"][0]["props"]["youtubeUrl"] = "https://www.youtube.com/embed/abcdefghijk"
    assert project_video_quota(p)["used"] == 1
    p["blocks"][0]["props"]["secondVideo"] = "https://example.test/video.mp4"
    with pytest.raises(NuvlyError):
        validate_project_media_quota(p)


def test_invitation_images_and_video_poster_are_included():
    p = {
        "productType": "invitation",
        "images": {"heroImage": "/assets/hero.jpg", "galleryImages": [{"src": "/assets/gallery.jpg"}]},
        "invitationData": {"videoPoster": "/assets/poster.jpg"},
    }
    assert website_image_quota(p)["used"] == 3


def test_advanced_video_requires_external_link():
    p = project(1, "pro")
    p["blocks"][0]["props"]["videoUrl"] = "/static/uploads/video.mp4"
    with pytest.raises(NuvlyError) as error:
        validate_project_media_quota(p)
    assert error.value.code == "EXTERNAL_VIDEO_REQUIRED"


@pytest.mark.parametrize("location", ["blocks", "pages", "linked", "websiteData"])
def test_disabled_starter_video_does_not_block_save(location):
    video = {
        "type": "youtubeVideo",
        "variant": "YVE1-YouTube-Embed",
        "enabled": False,
        "props": {"videoUrl": "https://www.youtube.com/watch?v=DKSWor9pomI", "coverImage": "/assets/poster.jpg"},
    }
    p = {
        "blocks": {"blocks": [video]},
        "pages": {"pages": [{"blocks": [video]}]},
        "linked": {"metadata": {"linkedPages": [{"blocks": [video]}]}},
        "websiteData": {"websiteData": {"blocks": [video]}},
    }[location]
    p["planTier"] = "plus"
    assert project_video_quota(p)["used"] == 0
    assert website_image_quota(p)["used"] == 1
    validate_project_media_quota(p)
    video["enabled"] = True
    with pytest.raises(NuvlyError) as error:
        validate_project_media_quota(p)
    assert error.value.code == "VIDEO_QUOTA_EXCEEDED"


def test_save_ignores_video_defaults_unused_by_selected_variants():
    hero = {
        "type": "hero",
        "variant": "HE2-Split-Screen",
        "props": {"videoUrl": "https://www.youtube.com/watch?v=DKSWor9pomI", "mediaImage": "/assets/hero.jpg"},
    }
    proof = {
        "type": "socialProof",
        "variant": "PSE1-Infinite-Marquee",
        "settings": {"proofVideoUrl1": "https://youtu.be/abcdefghijk"},
    }
    p = {
        "planTier": "plus",
        "pages": [{"blocks": [hero]}],
        "metadata": {"linkedPages": [{"blocks": [proof]}]},
        "websiteData": {"blocks": [hero, proof]},
    }
    assert project_video_quota(p)["used"] == 0
    assert website_image_quota(p)["used"] == 1
    validate_project_media_quota(p)
    for block, variant in ((hero, "HP2-Editorial-Video-Youtube"), (proof, "PSP2-Video-Grid")):
        previous = block["variant"]
        block["variant"] = variant
        with pytest.raises(NuvlyError) as error:
            validate_project_media_quota(p)
        assert error.value.code == "VIDEO_QUOTA_EXCEEDED"
        block["variant"] = previous
