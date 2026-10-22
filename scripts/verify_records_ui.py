#!/usr/bin/env python3
"""Run an isolated real-browser smoke test. Never connects to an existing database.

Prerequisites: built frontend, backend test dependencies, playwright + Chromium.
Example: PYTHONPATH=backend python scripts/verify_records_ui.py --output artifacts/ui
Screenshots use synthetic fixtures, not native HIOKI compatibility evidence.
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import time
import traceback
import uuid
import zipfile

import httpx
from playwright.sync_api import sync_playwright, expect


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=Path('artifacts/ui'))
    args = parser.parse_args()
    output = args.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    repo = Path(__file__).resolve().parents[1]
    report: dict = {'fixtures': 'synthetic only', 'checks': [], 'errors': []}
    with tempfile.TemporaryDirectory(prefix='hioki-ui-') as directory:
        root = Path(directory)
        with socket.socket() as sock:
            sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
        env = os.environ.copy(); env['PYTHONPATH'] = str(repo / 'backend')
        code = ('from pathlib import Path; import uvicorn; '
                'from fastapi.staticfiles import StaticFiles; '
                'from app.main import create_app; from app.config import Settings; '
                f'app=create_app(Settings(database_url="sqlite+pysqlite:///{root / "test.db"}",archive_root=Path({str(root / "archives")!r}))); '
                f'app.mount("/",StaticFiles(directory={str(repo / "frontend/dist")!r},html=True)); '
                f'uvicorn.run(app,host="127.0.0.1",port={port},log_level="warning")')
        with (output / 'server.log').open('w') as log:
            server = subprocess.Popen([sys.executable, '-c', code], env=env, stdout=log, stderr=subprocess.STDOUT)
            try:
                base = f'http://127.0.0.1:{port}'
                client = httpx.Client(base_url=base, timeout=20)
                for _ in range(100):
                    try:
                        if client.get('/api/health').status_code == 200: break
                    except httpx.TransportError: pass
                    if server.poll() is not None: raise RuntimeError('test server exited; inspect server.log')
                    time.sleep(0.1)
                else: raise RuntimeError('test server did not become healthy')
                project_uuid = str(uuid.uuid4()); zipped = io.BytesIO()
                with zipfile.ZipFile(zipped, 'w') as archive:
                    archive.writestr('温度試験.gprj', json.dumps({'id': project_uuid}))
                response = client.post('/api/projects/import', files={'archive': (project_uuid + '.zip', zipped.getvalue())}, data={'source_uuid': project_uuid})
                response.raise_for_status(); project = response.json()
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch()
                    context = browser.new_context(viewport={'width': 1280, 'height': 800}, locale='ja-JP', timezone_id='Asia/Tokyo')
                    page = context.new_page()
                    page.on('pageerror', lambda error: report['errors'].append(str(error)))
                    page.goto(base + '/#records')
                    expect(page.get_by_text('該当する記録はありません。')).to_be_visible()
                    page.screenshot(path=str(output / 'empty.png'))
                    report['checks'].append('empty state')
                    page.get_by_label('GRCDファイル', exact=True).set_input_files({'name': '温度試験.grcd', 'mimeType': 'application/octet-stream', 'buffer': b'opaque-native-fixture-not-a-real-grcd'})
                    expect(page.get_by_text('1 件登録', exact=False)).to_be_visible()
                    item = client.get('/api/records').json()['items'][0]
                    assert item['project_id'] == project['id'] and item['inspection']['status'] == 'unavailable'
                    report['checks'].append('UI import, automatic association, opaque preservation')
                    menu_button = page.get_by_role('button', name='温度試験 の操作', exact=True)
                    menu_button.click()
                    expect(page.get_by_role('menu')).to_be_visible()
                    page.get_by_role('menuitem', name='CSVを関連付け', exact=True).click()
                    dialog = page.get_by_role('dialog')
                    csv_data = 'timestamp,温度 [°C],メモ\r\n2026-10-22T10:00:00,20.100000001,通常\r\n2026-10-22T10:01:00,-2.5,=1+1\r\n2026-10-22T10:02:00,25.2,最高\r\n'
                    dialog.get_by_label('CSV（先頭行は列名・最大32 MiB）', exact=True).set_input_files({'name': 'readings.csv', 'mimeType': 'text/csv', 'buffer': csv_data.encode('utf-8-sig')})
                    dialog.get_by_label('日時列名（任意）', exact=True).fill('timestamp')
                    dialog.get_by_role('button', name='保存', exact=True).click()
                    expect(dialog).not_to_be_visible()
                    expect(page.get_by_role('cell', name='関連付けCSV', exact=True)).to_be_visible()
                    report['checks'].append('companion CSV upload with explicit Asia/Tokyo timestamps')
                    row = page.get_by_role('row').filter(has=page.get_by_role('cell', name='温度試験', exact=True))
                    row.click(button='right')
                    expect(page.get_by_role('menu')).to_be_visible()
                    page.screenshot(path=str(output / 'desktop-menu.png'))
                    page.keyboard.press('Escape')
                    row.focus(); page.keyboard.press('Shift+F10')
                    expect(page.get_by_role('menu')).to_be_visible()
                    page.keyboard.press('ArrowDown'); page.keyboard.press('Enter')
                    expect(page.get_by_role('dialog')).to_be_visible()
                    page.get_by_label('記録名', exact=True).fill('温度試験（確認済み）')
                    page.get_by_label('メモ', exact=True).fill('CSV照合用の合成データ')
                    page.get_by_role('dialog').get_by_role('button', name='保存', exact=True).click()
                    expect(page.get_by_role('cell', name='温度試験（確認済み）', exact=True)).to_be_visible()
                    report['checks'].append('right-click, Escape, Shift+F10, arrow selection, edit dialog')
                    page.get_by_role('button', name='温度試験（確認済み） の操作', exact=True).click()
                    page.get_by_role('menuitem', name='データを開く', exact=True).click()
                    detail = page.get_by_role('region', name='記録データ', exact=True)
                    expect(detail.get_by_role('cell', name='20.100000001', exact=True)).to_be_visible()
                    detail.get_by_role('button', name='温度 [°C]', exact=True).click()
                    expect(detail.get_by_role('row').nth(1)).to_contain_text('-2.5')
                    with page.expect_download() as download_info:
                        detail.get_by_role('button', name='絞り込み結果をCSV出力', exact=True).click()
                    exported = download_info.value
                    exported.save_as(str(output / 'export.csv'))
                    assert "'=1+1" in (output / 'export.csv').read_text(encoding='utf-8-sig')
                    detail.get_by_label('表内検索', exact=True).fill('最高')
                    expect(detail.get_by_role('cell', name='25.2', exact=True)).to_be_visible()
                    expect(detail.get_by_role('cell', name='-2.5', exact=True)).not_to_be_visible()
                    detail.get_by_label('表内検索', exact=True).fill('')
                    expect(detail.get_by_role('cell', name='-2.5', exact=True)).to_be_visible()
                    detail.scroll_into_view_if_needed(); page.screenshot(path=str(output / 'desktop-data.png'))
                    report['checks'].append('table sort/search, precision preservation, browser CSV download and formula neutralization')
                    page.get_by_role('button', name='詳細を閉じる', exact=True).click()
                    page.get_by_role('button', name='温度試験（確認済み） の操作', exact=True).click()
                    page.get_by_role('menuitem', name='削除', exact=True).click()
                    page.get_by_role('dialog').get_by_role('button', name='削除', exact=True).click()
                    expect(page.get_by_text('該当する記録はありません。')).to_be_visible()
                    page.get_by_label('削除済みを含める', exact=True).check()
                    page.get_by_role('button', name='温度試験（確認済み） の操作', exact=True).click()
                    page.get_by_role('menuitem', name='削除済みから復帰', exact=True).click()
                    expect(page.get_by_role('cell', name='関連付けCSV', exact=True)).to_be_visible()
                    report['checks'].append('delete and restore without losing data')
                    # Long filenames and many rows exercise clipping and list pagination.
                    for number in range(52):
                        response = client.post('/api/records/import', files={'record': (f'長い名称の温度・電力比較試験データ_{number:02d}.grcd', f'opaque-{number}'.encode())})
                        response.raise_for_status()
                    page.get_by_role('button', name='更新', exact=True).click()
                    expect(page.get_by_text('1–50 / 53 件', exact=True)).to_be_visible()
                    page.get_by_role('button', name='次へ', exact=True).click()
                    expect(page.get_by_text('51–53 / 53 件', exact=True)).to_be_visible()
                    page.get_by_role('button', name='前へ', exact=True).click()
                    report['checks'].append('many records, long names, server-side pagination')
                    page.get_by_label('検索', exact=True).fill('確認済み')
                    expect(page.get_by_text('1–1 / 1 件', exact=True)).to_be_visible()
                    page.set_viewport_size({'width': 390, 'height': 844})
                    expect(page.get_by_role('button', name='GRCDを登録', exact=True)).to_be_visible()
                    page.screenshot(path=str(output / 'mobile-list.png'))
                    page.get_by_role('button', name='温度試験（確認済み） の操作', exact=True).click()
                    menu = page.get_by_role('menu')
                    expect(menu).to_be_visible()
                    box = menu.bounding_box()
                    assert box and box['x'] >= 0 and box['x'] + box['width'] <= 391 and box['y'] >= 0
                    page.screenshot(path=str(output / 'mobile-menu.png'))
                    page.keyboard.press('Escape')
                    page.set_viewport_size({'width': 1280, 'height': 800})
                    page.get_by_role('button', name='プロジェクト', exact=True).click()
                    expect(page.get_by_role('navigation', name='データの種類')).to_be_visible()
                    page.get_by_role('button', name='レコードデータ', exact=True).click()
                    expect(page.get_by_label('検索', exact=True)).to_have_value('確認済み')
                    report['checks'].append('390px viewport, menu clamping, workspace state continuity')
                    assert not report['errors'], report['errors']
                    context.close(); browser.close()
                report['status'] = 'passed'
            except Exception:
                report['status'] = 'failed'; report['error'] = traceback.format_exc()
            finally:
                server.terminate()
                try: server.wait(timeout=10)
                except subprocess.TimeoutExpired: server.kill(); server.wait()
    (output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
