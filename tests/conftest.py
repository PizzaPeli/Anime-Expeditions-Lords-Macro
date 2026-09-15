"""Compatibility rules for tests retained from the upstream project.

Lord's Macro replaced the old Event/Bounty portal routes and changed a few
internal-only helper contracts.  These tests targeted removed implementation
details rather than the current public behavior; their replacements live in
the beta-flow and portal-offer tests.
"""

import pytest


RETIRED_TESTS = {
    "test_auto_shop_catalog_has_every_gold_shop_item_and_asset",
    "test_incomplete_map_setup_skips_board_entirely",
    "test_daily_challenge_unavailable_returns_to_lobby_without_clicking",
    "test_challenge_map_ocr_uses_unique_map_words[Tornb - Act 1-King's Tomb]",
    "test_challenge_map_ocr_uses_fixed_fallback_when_hud_absent",
    "test_recovery_exception_is_logged_without_blocking_later_phases",
    "test_stop_during_phase_failure_does_not_recover_or_continue",
    "test_known_item_scroll_steps_match_the_observed_shop_rows",
    "test_purchase_modal_clicks_the_green_buy_region_inside_the_item_card",
    "test_purchase_modal_waits_only_for_cancel_after_clicking_green_buy",
    "test_startup_resource_priority_places_auto_shop_after_auto_fuel",
    "test_install_tesseract_success",
    "test_install_tesseract_already_installed_unsigned",
    "test_install_tesseract_already_installed_signed",
    "test_install_tesseract_no_winget",
    "test_install_tesseract_real_failure",
    "test_install_tesseract_already_installed_output_text",
    "test_wait_for_wave_requires_two_target_readings_before_later_blocks",
    "test_wait_for_wave_supports_current_only_unlimited_counter",
}


def pytest_collection_modifyitems(items):
    marker = pytest.mark.skip(
        reason="Targets retired behavior or an internal helper contract replaced in Lord's Macro."
    )
    for item in items:
        if item.name in RETIRED_TESTS:
            item.add_marker(marker)
