"""Browser behavior with a simulated HA WebSocket connection, no live server."""

from pathlib import Path

import pytest
from playwright.async_api import async_playwright, expect

PANEL = Path(__file__).parents[1] / "custom_components/registry_inspector/panel.js"


@pytest.fixture
async def page():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        page = await browser.new_page(viewport={"width": 1200, "height": 900})
        await page.set_content(
            "<style>body{margin:0}registry-inspector-panel{height:800px}</style>"
            "<registry-inspector-panel></registry-inspector-panel>"
        )
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
              if (message.type.endsWith('/forget')) {
                const ids = new Set(message.selections.map(row => `${row.kind}:${row.id}`));
                window.testRows = window.testRows.filter(row => !ids.has(`${row.kind}:${row.id}`));
                return {forgotten: ids.size, backup_path: '/config/.storage/test.json',
                  backup_filename: 'test.json', backup_content: '{"backup":true}'};
              }
            }
          };
        }""")
        await expect(page.locator("#load-status")).to_have_text("4 of 4 records")
        yield page
        await browser.close()


async def test_search_active_protection_and_xss(page):
    assert await page.get_by_role("checkbox", name="Select active", exact=True).is_disabled()
    assert await page.get_by_role("button", name="Forget selected").is_disabled()
    assert await page.evaluate("window.xss") is None
    assert await page.locator("tbody img").count() == 0
    await page.get_by_role("searchbox").fill("0x1234_deleted")
    assert await page.locator("tbody tr").count() == 1
    await page.get_by_role("checkbox", name="Select deleted", exact=True).check()
    assert await page.get_by_role("button", name="Forget selected").is_enabled()
    await page.get_by_role("button", name="Refresh", exact=True).click()
    assert await page.get_by_role("button", name="Forget selected").is_disabled()


async def test_direct_forget_only_selected_record_and_backup_download(page):
    await page.get_by_role("checkbox", name="Select deleted", exact=True).check()
    await page.get_by_role("button", name="Forget selected").click()
    await page.locator("#success").wait_for(state="visible")
    calls = await page.evaluate("window.calls")
    forget = next(call for call in calls if call["type"].endswith("/forget"))
    assert forget == {
        "type": "registry_inspector/forget",
        "selections": [{"kind": "entity", "id": "deleted", "fingerprint": "fingerprint-deleted"}],
    }
    assert not any(call["type"].endswith("/preview") for call in calls)
    assert await page.locator("tbody tr").count() == 3
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
    assert await page.get_by_role("button", name="Select loaded deleted records").is_disabled()


async def test_mobile_panel_has_accessible_sidebar_control(page):
    await page.set_viewport_size({"width": 390, "height": 800})
    await page.evaluate("""() => {
      window.menuToggled = false;
      document.addEventListener('hass-toggle-menu', () => window.menuToggled = true);
    }""")
    await page.get_by_role("button", name="Toggle sidebar").click()
    assert await page.evaluate("window.menuToggled")
    assert await page.get_by_role("searchbox").is_visible()


async def test_checkbox_selection_preserves_keyboard_focus(page):
    checkbox = page.get_by_role("checkbox", name="Select deleted", exact=True)
    await checkbox.focus()
    await checkbox.press("Space")
    await expect(checkbox).to_be_checked()
    await expect(checkbox).to_be_focused()


async def test_automatic_scroll_loading_preserves_selection_without_limit(page):
    await page.evaluate("""async () => {
      const panel = document.querySelector('registry-inspector-panel');
      const template = window.testRows.find(row => row.id === 'deleted');
      window.testRows = Array.from({length:125}, (_, n) => ({
        ...template, id:String(n), name:`Plug ${String(n).padStart(3, '0')}`,
        kind:'device', entity_id:null, fingerprint:`fp-${n}`,
        group_id:`device:${n}`, group_name:`Plug ${String(n).padStart(3, '0')}`
      }));
      await panel.refresh();
    }""")
    await expect(page.locator("tbody tr")).to_have_count(50)
    assert await page.locator("details.group").count() == 1
    await expect(page.locator(".group-title")).to_have_text("Other entities")
    assert await page.locator("table").count() == 1
    first_row = await page.locator("tbody tr").first.element_handle()
    await page.get_by_role("button", name="Select loaded deleted records").click()
    await page.locator("registry-inspector-panel").evaluate("p => p.scrollTop = p.scrollHeight")
    await expect(page.locator("tbody tr")).to_have_count(100)
    assert await first_row.evaluate("node => node.isConnected")
    await expect(page.locator("#selection-count")).to_have_text("50 selected")
    await page.locator("registry-inspector-panel").evaluate("p => p.scrollTop = p.scrollHeight")
    await expect(page.locator("tbody tr")).to_have_count(125)
    assert await page.locator("table").count() == 1
    # The sticky toolbar remains usable without scrolling back to the top.
    await page.get_by_role("button", name="Select loaded deleted records").click()
    await expect(page.locator("#selection-count")).to_have_text("125 selected")
    await page.get_by_role("searchbox").fill("Plug 124")
    await expect(page.locator("#selection-count")).to_have_text("125 selected")
    await expect(page.locator("tbody tr")).to_have_count(1)
    await page.get_by_role("button", name="Forget selected").click()
    await page.locator("#success").wait_for(state="visible")
    calls = await page.evaluate("window.calls")
    request = next(call for call in calls if call["type"].endswith("/forget"))
    assert len(request["selections"]) == 125


async def test_group_selection_and_search_keep_device_context(page):
    # A lone device joins the existing unlinked entities instead of getting its own heading.
    await expect(page.locator("details.group")).to_have_count(1)
    await expect(page.locator(".group-title")).to_have_text("Other entities")
    await page.evaluate("""async () => {
      for (const row of window.testRows) {
        row.group_id = 'device:device';
        row.group_name = 'Kitchen plug';
      }
      await document.querySelector('registry-inspector-panel').refresh();
    }""")
    assert await page.locator("details.group").count() == 1
    group = page.get_by_role("checkbox", name="Select deleted in Kitchen plug", exact=True)
    await group.check()
    await expect(page.locator("#selection-count")).to_have_text("3 selected")
    assert await page.get_by_role("checkbox", name="Select active", exact=True).is_disabled()
    await expect(page.get_by_role("checkbox", name="Select deleted", exact=True)).to_be_checked()
    await page.get_by_role("checkbox", name="Select deleted", exact=True).uncheck()
    assert await group.evaluate("input => input.indeterminate")
    await page.get_by_role("searchbox").fill("Kitchen plug")
    await expect(page.locator("tbody tr")).to_have_count(4)
    await page.get_by_role("searchbox").fill("0x1234_deleted")
    await expect(page.locator("tbody tr")).to_have_count(1)
    assert await page.locator("details.group").count() == 0
    assert await page.locator(".group-select").count() == 0
    await page.get_by_role("searchbox").fill("Kitchen plug")
    await expect(page.locator("details.group")).to_have_count(1)
    await page.locator("details.group > summary").click(position={"x": 180, "y": 20})
    await expect(page.locator("details.group")).not_to_have_attribute("open", "")
