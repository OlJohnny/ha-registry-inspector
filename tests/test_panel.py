"""Browser behavior with a simulated HA WebSocket connection, no live server."""

from pathlib import Path

import pytest
from playwright.async_api import async_playwright

PANEL = Path(__file__).parents[1] / "custom_components/registry_inspector/panel.js"


@pytest.fixture
async def page():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={"width": 1200, "height": 900})
        await page.set_content("<registry-inspector-panel></registry-inspector-panel>")
        await page.add_script_tag(path=str(PANEL))
        await page.evaluate("""() => {
          const row = (id, deleted, kind = 'entity') => ({
            id, kind, deleted, name: id, entity_id: kind === 'entity' ? 'switch.' + id : null,
            section: deleted ? 'deleted_entities' : 'entities',
            fingerprint: 'fingerprint-' + id, integration: 'mqtt', area: 'Kitchen',
            state: deleted ? null : 'unavailable', disabled: false,
            record: {id, unique_id: '0x1234_' + id, name: id}
          });
          window.testRows = [row('active', false), row('deleted', true),
            row('device', true, 'device'),
            row('<img src=x onerror=window.xss=true>', true)];
          window.calls = [];
          document.querySelector('registry-inspector-panel').hass = {
            callWS: async (message) => {
              window.calls.push(message);
              if (message.type.endsWith('/list')) return {rows: window.testRows};
              if (message.type.endsWith('/preview')) return {
                token: 'reviewed-token', records: message.selections.map(selection => ({
                  section: 'deleted_entities',
                  record: window.testRows.find(r => r.id === selection.id).record
                }))
              };
              if (message.type.endsWith('/forget')) {
                window.testRows = window.testRows.filter(row => !row.deleted);
                return {forgotten: 1, backup_path: '/config/.storage/test.json',
                  backup_filename: 'test.json', backup_content: '{"backup":true}'};
              }
            }
          };
        }""")
        await page.locator("#page").get_by_text("4 matches", exact=False).wait_for()
        yield page
        await browser.close()


async def test_search_active_protection_and_xss(page):
    assert await page.get_by_role("checkbox", name="Select active", exact=True).is_disabled()
    assert await page.get_by_role("button", name="Preview forgetting").is_disabled()
    assert await page.evaluate("window.xss") is None
    assert await page.locator("tbody img").count() == 0
    await page.get_by_role("searchbox").fill("0x1234_deleted")
    assert await page.locator("tbody tr").count() == 1
    await page.get_by_role("checkbox", name="Select deleted", exact=True).check()
    assert await page.get_by_role("button", name="Preview forgetting").is_enabled()
    await page.get_by_role("button", name="Refresh", exact=True).click()
    assert await page.get_by_role("button", name="Preview forgetting").is_disabled()


async def test_preview_confirm_and_backup_download(page):
    await page.get_by_role("checkbox", name="Select deleted", exact=True).check()
    await page.get_by_role("button", name="Preview forgetting").click()
    dialog = page.locator("#confirmation")
    await dialog.wait_for(state="visible")
    assert await dialog.get_by_role("button", name="Forget saved settings").is_disabled()
    await dialog.get_by_role("checkbox").check()
    await dialog.get_by_role("button", name="Forget saved settings").click()
    await page.locator("#success").wait_for(state="visible")
    calls = await page.evaluate("window.calls")
    preview = next(call for call in calls if call["type"].endswith("/preview"))
    assert len(preview["selections"]) == 1
    assert preview["selections"][0]["id"] == "deleted"
    forget = next(call for call in calls if call["type"].endswith("/forget"))
    assert forget == {"type": "registry_inspector/forget", "token": "reviewed-token"}
    assert await page.locator("tbody tr").count() == 1
    async with page.expect_download() as download:
        await page.get_by_role("button", name="Download backup").click()
    assert (await download.value).suggested_filename == "test.json"


async def test_read_only_compatibility_message(page):
    await page.evaluate("""() => {
      const panel = document.querySelector('registry-inspector-panel');
      panel.writeDisabledReason = 'Unsupported HA version';
      panel.render();
    }""")
    assert await page.locator("#compatibility").inner_text() == "Unsupported HA version"
    assert await page.get_by_role("checkbox", name="Select deleted", exact=True).is_disabled()
    assert await page.get_by_role("button", name="Select deleted on this page").is_disabled()


async def test_mobile_panel_has_accessible_sidebar_control(page):
    await page.set_viewport_size({"width": 390, "height": 800})
    await page.evaluate("""() => {
      window.menuToggled = false;
      document.addEventListener('hass-toggle-menu', () => window.menuToggled = true);
    }""")
    await page.get_by_role("button", name="Toggle sidebar").click()
    assert await page.evaluate("window.menuToggled")
    assert await page.get_by_role("searchbox").is_visible()
