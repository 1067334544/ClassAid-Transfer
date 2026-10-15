# SPDX-FileCopyrightText: 2026 ClassAid-Transfer contributors
#
# SPDX-License-Identifier: AGPL-3.0-only

""" The optional theme hook in Gen-Ed's base.html: ClassAid restyles Bulma; CodeHelp is unchanged. """

from pathlib import Path

import codehelp
from tests.conftest import AppClient


def test_classaid_pages_load_theme(client: AppClient) -> None:
    for path in ('/', '/auth/login'):
        html = client.get(path).text
        assert '/static/theme.css' in html
        assert '/static/bulma-theme.css' in html


def test_theme_assets_served(client: AppClient) -> None:
    for asset in ('theme.css', 'bulma-theme.css'):
        response = client.get(f'/static/{asset}')
        assert response.status_code == 200
        assert '--ca-' in response.text


def test_codehelp_unaffected_by_theme_hook(tmp_path: Path) -> None:
    app = codehelp.create_app(test_config={'TESTING': True, 'DATABASE': str(tmp_path / 'ch.db')}, instance_path=tmp_path)
    html = app.test_client().get('/').text
    assert 'bulma.min.css' in html
    assert 'theme.css' not in html
