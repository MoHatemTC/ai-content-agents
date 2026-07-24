from frontend.qbank_ui import render


def test_qbank_ui_render_exists():
    assert callable(render)


def test_qbank_ui_render_runs():
    result = render()

    assert result is None