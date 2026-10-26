from app.tools.display_path import display_file_path, display_path_text

UUID = "6db170c9-ea2b-4036-84d1-47260c687014"


def test_display_file_path_has_required_cases():
    assert display_file_path(f"{UUID}/README.md") == "README.md"
    assert display_file_path(f"{UUID}/campus_signup/api.py") == "campus_signup/api.py"
    assert display_file_path("runtime/pytest-output.txt") == "runtime/pytest-output.txt"


def test_display_path_text_removes_only_uuid_prefixes():
    assert (
        display_path_text(f"规则层另有未发送材料：{UUID}/README.md:1-9。")
        == "规则层另有未发送材料：README.md:1-9。"
    )
