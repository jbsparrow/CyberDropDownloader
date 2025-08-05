from cyberdrop_dl.utils import json


def test_json_load_js_obj():
    string = """
    {
        unquoted_key: 'and you can quote me on that',
        lineBreaks: "test, 1 2 3! No \\n's!",
        "quoted_key": "like normal JSON",
    }
    """
    expected = {
        "unquoted_key": "and you can quote me on that",
        "lineBreaks": "test, 1 2 3! No \n's!",
        "quoted_key": "like normal JSON",
    }
    assert json.load_js_obj(string) == expected
